"""One-shot: export each slide of PortfolioIQ_January2026.pptx as PNG.

Uses PowerPoint COM (Office must be installed). Outputs to public/thumbnails/.

Run from website/ folder:
    python _export_thumbnails.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
PPTX = HERE / "public" / "PortfolioIQ_January2026.pptx"
OUT_DIR = HERE / "public" / "thumbnails"


def export_via_powerpoint() -> int:
    try:
        import comtypes.client
    except ImportError:
        print("comtypes not installed; run: pip install comtypes")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Opening PowerPoint to export {PPTX.name} ...")

    ppt = comtypes.client.CreateObject("PowerPoint.Application")
    # PowerPoint 2013+ requires the window to be visible to export.
    try:
        ppt.Visible = 1
    except Exception:
        pass

    deck = ppt.Presentations.Open(str(PPTX), WithWindow=False)
    print(f"  loaded {deck.Slides.Count} slides")

    # Export each slide individually for control over filename and size.
    # 1600x900 keeps the 16:9 ratio and is plenty for web thumbnails.
    for i in range(1, deck.Slides.Count + 1):
        out = OUT_DIR / f"slide_{i:02d}.png"
        deck.Slides(i).Export(str(out), "PNG", 1600, 900)
        print(f"  -> {out.name}")

    deck.Close()
    ppt.Quit()
    print(f"\nDone. {deck.Slides.Count} thumbnails in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    if not PPTX.exists():
        print(f"ERROR: {PPTX} not found")
        sys.exit(1)
    sys.exit(export_via_powerpoint())
