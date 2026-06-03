"""build_period_pptxs.py — pragmatic per-period PPTX builder.

LIMITATION: gtsimogiannis's spec/parts/ folder is missing the 9 slide XML files
in our local copy (OneDrive Files-On-Demand never synced them). Until those
files arrive, we can't run his Jinja2 renderer to produce true per-period decks.

This script is a tactical workaround:
- Take the fully-rendered Jan 2026 PPTX (which IS on disk)
- Unzip + text-replace period strings inside the slide XMLs
- Re-zip as PortfolioIQ_<Period>.pptx

What changes per period: cover title date, footer period, issue date, "FY2026"
label where the period year matters.

What stays as Jan (the honest limitation): KPI tile numbers, table rows,
chart values, narrative text. We can't recompute these without the parts/
folder.

When gtsimogiannis re-shares the missing files, use render_decks.py instead
for proper per-period rendering.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE     = Path(__file__).resolve().parent.parent
JAN_PPTX = BASE / "website" / "public" / "PortfolioIQ_January2026.pptx"
PUBLIC   = BASE / "website" / "public"
# Immutable source — colleague's original render. Restore the website copy
# from this on every build so patches don't compound across runs.
JAN_PPTX_SOURCE = BASE / "input" / "Agentic Status Report" / "Fabric" / "presentations" / "pptxs" / "ProjectsStatusUpdate_January2026_v7.pptx"

# Order matters — more-specific replacements must come BEFORE more-general ones
# (so "01 FEBRUARY 2026" gets matched first, then any remaining "FEBRUARY 2026").
PERIOD_BUILDS = [
    {
        "filename": "PortfolioIQ_December2025.pptx",
        "display":  "December 2025",
        "replacements": [
            # issue date (cover slide)
            ("01 FEBRUARY 2026", "01 JANUARY 2026"),
            # period label in cover + every footer
            ("January 2026", "December 2025"),
            # FY label
            ("FY2026 ", "FY2025–2026 "),
        ],
    },
    {
        "filename": "PortfolioIQ_February2026.pptx",
        "display":  "February 2026",
        "replacements": [
            ("01 FEBRUARY 2026", "01 MARCH 2026"),
            ("January 2026", "February 2026"),
        ],
    },
]


def build_variant(spec: dict) -> Path:
    out = PUBLIC / spec["filename"]
    if out.exists():
        out.unlink()

    rewrites = 0
    with zipfile.ZipFile(JAN_PPTX, "r") as src, \
         zipfile.ZipFile(out,      "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            # Only attempt text-replace on XML / rels parts
            if item.filename.endswith((".xml", ".rels")):
                try:
                    text = data.decode("utf-8")
                    before = text
                    for old, new in spec["replacements"]:
                        text = text.replace(old, new)
                    if text != before:
                        rewrites += sum(before.count(old) for old, _ in spec["replacements"] if old in before)
                        data = text.encode("utf-8")
                except UnicodeDecodeError:
                    pass
            dst.writestr(item, data)

    print(f"  built {out.name} ({out.stat().st_size:,} bytes, {rewrites} text replacements)")
    return out


def main():
    # Re-seed the Jan deck from the immutable source so re-runs don't compound patches
    if JAN_PPTX_SOURCE.exists():
        import shutil
        shutil.copy2(JAN_PPTX_SOURCE, JAN_PPTX)
        print(f"Restored Jan deck from immutable source: {JAN_PPTX_SOURCE.name}")
    if not JAN_PPTX.exists():
        sys.exit(f"ERROR: {JAN_PPTX} not found. Need the rendered Jan deck as source.")
    print(f"Source: {JAN_PPTX.name} ({JAN_PPTX.stat().st_size:,} bytes)")
    print("Building period variants by text-replace on the Jan deck:")
    print()
    for spec in PERIOD_BUILDS:
        build_variant(spec)
    print()
    print("Done. 3 PPTXs in website/public/:")
    for fn in ["PortfolioIQ_December2025.pptx", "PortfolioIQ_January2026.pptx", "PortfolioIQ_February2026.pptx"]:
        p = PUBLIC / fn
        if p.exists():
            print(f"  {fn:<40}  {p.stat().st_size:>8,} bytes")
    print()
    print("NOTE: KPI data inside Dec/Feb decks is still January numbers.")
    print("      Restore the missing parts/ files from gtsimogiannis and run render_decks.py")
    print("      to produce true per-period decks.")


if __name__ == "__main__":
    main()
