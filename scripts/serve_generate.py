"""serve_generate.py — local demo server that serves the website AND renders decks live.

Use this instead of `python -m http.server` when you want the dashboard's "Generate"
button to actually build a fresh PPTX from the data (rather than replay a pre-built one).

    python scripts/serve_generate.py            # http://localhost:8000

Endpoints:
  GET  /api/generate?period=YYYY-MM   -> renders that period and returns the .pptx
  (everything else)                   -> static files from website/

The build calls render_decks.build_one(), the same renderer used by the batch pipeline.
On the static Vercel site this endpoint does not exist, so the front-end falls back to
the pre-rendered replay automatically.
"""
from __future__ import annotations

import io
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
WEBSITE = BASE / "website"
SCRIPTS = BASE / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_live  # noqa: E402  (after sys.path tweak)

# Valid periods come from the dashboard JSON files (live data + csv backup).
def _valid_periods():
    found = set()
    for sub in ("data", "data_csv_backup"):
        for p in (WEBSITE / "public" / sub).glob("20*.json"):
            found.add(p.stem)
    return sorted(found)

# One build at a time: the renderer mutates a shared working tree.
_BUILD_LOCK = threading.Lock()
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class Handler(SimpleHTTPRequestHandler):
    def _json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/generate":
            return self._handle_generate(parse_qs(parsed.query))
        return super().do_GET()

    def _handle_generate(self, q):
        import time
        ymd = (q.get("period", [""])[0] or "").strip()
        valid = _valid_periods()
        if ymd not in valid:
            return self._json(400, {"error": f"unknown period {ymd!r}", "valid": valid})
        try:
            with _BUILD_LOCK:
                t0 = time.perf_counter()
                path = render_live.build(ymd)
                elapsed = round(time.perf_counter() - t0, 1)
            data = Path(path).read_bytes()
        except Exception as e:  # surface the reason; front-end falls back on non-200
            return self._json(500, {"error": "render failed", "detail": str(e)[:500]})

        filename = Path(path).name
        self.send_response(200)
        self.send_header("Content-Type", PPTX_MIME)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("X-Build-Seconds", str(elapsed))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print(f"  built {filename} for {ymd} in {elapsed}s ({len(data):,} bytes)")

    def log_message(self, fmt, *args):  # quieter console
        if "/api/generate" in (self.path or ""):
            super().log_message(fmt, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = partial(Handler, directory=str(WEBSITE))
    srv = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"Portfolio IQ demo server on http://localhost:{port}")
    print(f"  static : {WEBSITE}")
    print(f"  live   : GET /api/generate?period=YYYY-MM  -> {_valid_periods()}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
