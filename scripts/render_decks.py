"""render_decks.py — produce one PowerPoint per period using gtsimogiannis's renderer.

For each period (Dec 2025, Jan 2026, Feb 2026):
  1. Compute the period's KPIs from data/csv/ (reuses csv_to_jsons logic)
  2. Build 9 per-slide JSONs in HIS format (using his Jan JSONs as schema baseline,
     overwriting the data-driven fields with this period's numbers)
  3. Write the 9 JSONs into a working copy of his template tree
  4. Invoke his render.py via subprocess
  5. Copy the resulting .pptx to website/public/PortfolioIQ_<Period>.pptx

His original template tree under input/Agentic Status Report/ is treated as
READ-ONLY. We make a working copy under scripts/_renderer/ so each render
gets a clean values/ folder.

Run:
    python scripts/render_decks.py
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import date
from pathlib import Path

# Greek/Windows console can't print Unicode arrows; force utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Reuse the CSV reading + KPI helpers from csv_to_jsons
sys.path.insert(0, str(Path(__file__).resolve().parent))
from csv_to_jsons import (
    load_csv, load_dims, join_dims, lifetime_completed_count, parse_date, m, f, i,
    RAG_DECODE, CATEGORY_DISPLAY, CATEGORY_LEGEND, CATEGORY_COLOR, CATEGORY_ORDER,
)

BASE          = Path(__file__).resolve().parent.parent
HIS_SPEC      = BASE / "input" / "Agentic Status Report" / "Fabric" / "presentations" / "templates" / "ProjectsStatusUpdate_20260422_spec"
HIS_JAN_JSONS = BASE / "input" / "Agentic Status Report" / "Fabric" / "genai_agent_results" / "genai_agent_results" / "2026-01"
WORKING       = BASE / "scripts" / "_renderer"
PUBLIC        = BASE / "website" / "public"

# Map period_code → display + issue date + filename for the website
PERIODS = {
    "202512": {
        "ymd":          "2025-12",
        "display":      "December 2025",
        "issue_iso":    "2026-01-01",
        "issue_disp":   "01 JANUARY 2026",
        "filename":     "PortfolioIQ_December2025.pptx",
    },
    "202601": {
        "ymd":          "2026-01",
        "display":      "January 2026",
        "issue_iso":    "2026-02-01",
        "issue_disp":   "01 FEBRUARY 2026",
        "filename":     "PortfolioIQ_January2026.pptx",
    },
    "202602": {
        "ymd":          "2026-02",
        "display":      "February 2026",
        "issue_iso":    "2026-03-01",
        "issue_disp":   "01 MARCH 2026",
        "filename":     "PortfolioIQ_February2026.pptx",
    },
}


def setup_working_copy() -> Path:
    """Copy his spec tree to scripts/_renderer/ (fresh every run for cleanliness)."""
    if WORKING.exists():
        shutil.rmtree(WORKING)
    print(f"Cloning his renderer tree → {WORKING.relative_to(BASE)}")
    shutil.copytree(HIS_SPEC, WORKING)
    return WORKING


def patch_meta(jsons: dict[str, dict], period_info: dict) -> None:
    """Overwrite the meta fields on every slide JSON for this period."""
    for data in jsons.values():
        if "meta" in data:
            data["meta"]["reporting_period"]   = period_info["display"]
            data["meta"]["issue_date"]         = period_info["issue_iso"]
            data["meta"]["issue_date_display"] = period_info["issue_disp"]


def compute_per_period_aggregates(rows_all: list[dict], period_code: str, lifetime: int) -> dict:
    """Heavy lift — compute everything any per-slide JSON might need."""
    period_rows = [r for r in rows_all if r["REF_PERIOD"] == period_code]
    yyyy, mm = int(period_code[:4]), int(period_code[4:])
    period_dt = date(yyyy, mm, 1)

    def is_active(r):  return i(r.get("PROJECT_ACTIVE")) == 1
    def is_pending(r): return i(r.get("PROJECT_ACTIVE")) == 0 and i(r.get("PROJECT_COMPLETED")) == 0
    def is_rag(r):     return r.get("rag_code") in ("R", "A")
    def has_no_baseline(r): return not r.get("BASELINE_START_DATE")

    total   = len(period_rows)
    active  = sum(1 for r in period_rows if is_active(r))
    pending = sum(1 for r in period_rows if is_pending(r))
    overdue = sum(1 for r in period_rows
                  if is_active(r)
                  and i(r.get("PROJECT_COMPLETED")) == 0
                  and parse_date(r.get("BASELINE_PLANNED_COMPLETION_DATE"))
                  and parse_date(r["BASELINE_PLANNED_COMPLETION_DATE"]) < period_dt)
    overdue_pct = round((overdue / active * 100), 0) if active else 0

    budget_total_eur   = sum(f(r.get("BUDGET_CY")) for r in period_rows)
    budget_active_eur  = sum(f(r.get("BUDGET_CY")) for r in period_rows if is_active(r))
    budget_pending_eur = sum(f(r.get("BUDGET_CY")) for r in period_rows if is_pending(r))
    ytd_spend_ke       = sum(f(r.get("ACTUAL_CUMULATIVE_KE")) for r in period_rows)

    committed_budget_m = round(budget_total_eur   / 1_000_000, 1)
    budget_active_m    = round(budget_active_eur  / 1_000_000, 1)
    budget_pending_m   = round(budget_pending_eur / 1_000_000, 1)
    ytd_spend_m        = round(ytd_spend_ke       /     1_000, 1)
    ytd_spend_pct      = round((ytd_spend_m / committed_budget_m * 100), 1) if committed_budget_m else 0.0

    on_track     = sum(1 for r in period_rows if is_active(r) and r.get("schedule_kpi") == "On Track")
    delayed_lt20 = sum(1 for r in period_rows if is_active(r) and r.get("schedule_kpi") == "Delayed <= 20%")
    delayed_gt20 = sum(1 for r in period_rows if is_active(r) and r.get("schedule_kpi") == "Delayed > 20%")
    no_baseline  = sum(1 for r in period_rows if is_active(r) and has_no_baseline(r))
    schedule_headline_pct = round(((delayed_lt20 + delayed_gt20 + no_baseline) / active * 100), 0) if active else 0

    within_budget    = sum(1 for r in period_rows if is_active(r) and r.get("budget_kpi") == "Within Budget")
    overrun_risk     = sum(1 for r in period_rows if is_active(r) and (r.get("budget_kpi") or "").startswith("Over Budget"))
    within_budget_pct = round((within_budget / active * 100), 0) if active else 0
    ratios = [f(r["ACTUAL_CUMULATIVE_KE"]) * 1000 / f(r["BUDGET_CY"])
              for r in period_rows
              if is_active(r) and f(r.get("BUDGET_CY")) > 0]
    overrun_ceiling_pct = min(int(round(max(ratios) * 100)) if ratios else 0, 300)

    rag_rows = [r for r in period_rows if is_rag(r) and i(r.get("PROJECT_COMPLETED")) == 0]
    exposure_eur = sum(f(r.get("BUDGET_CY")) for r in rag_rows)
    exposure_m   = round(exposure_eur / 1_000_000, 1)
    rag_count    = len(rag_rows)

    cat_totals: dict[str, float] = {}
    for r in period_rows:
        cat = r.get("category_name") or ""
        if cat: cat_totals[cat] = cat_totals.get(cat, 0.0) + f(r.get("BUDGET_CY"))
    total_cat = sum(cat_totals.values()) or 1.0
    donut = []
    for full in CATEGORY_ORDER:
        v = cat_totals.get(full, 0.0)
        donut.append({
            "label":        CATEGORY_DISPLAY[full],
            "legend_label": CATEGORY_LEGEND[full],
            "value_m":      round(v / 1_000_000, 1),
            "pct":          int(round(v / total_cat * 100)),
            "color":        CATEGORY_COLOR[full],
        })

    def rag_weight(code): return {"R": 2, "A": 1}.get(code, 0)
    rag_rows_sorted = sorted(rag_rows, key=lambda r: (-rag_weight(r.get("rag_code")), -f(r.get("BUDGET_CY"))))
    a1_sorted       = sorted(rag_rows, key=lambda r: ({"R":0,"A":1}.get(r.get("rag_code"),2), -f(r.get("BUDGET_CY"))))

    return dict(
        period_dt=period_dt, year=yyyy,
        total=total, active=active, pending=pending,
        overdue=overdue, overdue_pct=overdue_pct,
        lifetime_completed=lifetime,
        committed_budget_m=committed_budget_m, budget_active_m=budget_active_m,
        budget_pending_m=budget_pending_m, ytd_spend_m=ytd_spend_m, ytd_spend_pct=ytd_spend_pct,
        on_track=on_track, delayed_lt20=delayed_lt20, delayed_gt20=delayed_gt20,
        no_baseline=no_baseline, schedule_headline_pct=int(schedule_headline_pct),
        within_budget=within_budget, overrun_risk=overrun_risk,
        within_budget_pct=int(within_budget_pct), overrun_ceiling_pct=overrun_ceiling_pct,
        exposure_m=exposure_m, rag_count=rag_count,
        donut=donut,
        rag_rows_ranked=rag_rows_sorted,
        rag_rows_a1=a1_sorted,
    )


def _date_format(d):
    if d is None: return "TBD"
    if isinstance(d, str):
        d = parse_date(d) or d
        if isinstance(d, str): return d
    return d.strftime("%b %Y")


def _highlights_template(row) -> str:
    parts = []
    if row.get("EST_PERCENTAGE_OF_WORK_COMPLETED"):
        parts.append(f"{int(f(row['EST_PERCENTAGE_OF_WORK_COMPLETED']))}% complete")
    if f(row.get("BUDGET_CY")) > 0:
        parts.append(f"{m(row.get('BUDGET_CY'))} CY budget")
    if row.get("NEW_ANTICIPATED_COMPLETION_DATE"):
        parts.append(f"target {_date_format(parse_date(row.get('NEW_ANTICIPATED_COMPLETION_DATE')))}")
    parts.append("Action: review with project owner")
    return " · ".join(parts)


def patch_data_fields(jsons: dict[str, dict], agg: dict, period_info: dict) -> None:
    """Overwrite the data-driven fields in each per-slide JSON.
    Narrative fields (LLM-authored decisions, key risks, etc.) keep Jan's text
    as a placeholder for synthetic periods — fine for the demo."""

    # --- 02 Portfolio Snapshot ---
    s = jsons["02_portfolio_snapshot.json"]["snapshot"]
    tile_accents = [
        "green",
        "green",
        "red" if agg["overdue"] > 0 else "green",
        "green",
        "amber" if 0 < agg["ytd_spend_pct"] <= 50 else ("red" if agg["ytd_spend_pct"] > 100 else "green"),
    ]
    s["tiles"] = {
        "total_projects":      agg["total"],
        "active_projects":     agg["active"],
        "pending_projects":    agg["pending"],
        "completed_count":     agg["lifetime_completed"],
        "overdue_count":       agg["overdue"],
        "overdue_pct_active":  int(agg["overdue_pct"]),
        "committed_budget_m":  agg["committed_budget_m"],
        "budget_active_m":     agg["budget_active_m"],
        "budget_pending_m":    agg["budget_pending_m"],
        "ytd_spend_pct":       agg["ytd_spend_pct"],
        "ytd_spend_m":         agg["ytd_spend_m"],
        "currency":            "EUR",
        "tile_accents":        tile_accents,
    }
    s["schedule_card"] = {
        "headline_pct":      agg["schedule_headline_pct"],
        "on_track_count":    agg["on_track"],
        "delayed_big_count": agg["delayed_gt20"],
        "no_baseline_count": agg["no_baseline"],
    }
    s["budget_card"] = {
        "within_budget_pct":   agg["within_budget_pct"],
        "overrun_risk_count":  agg["overrun_risk"],
        "overrun_ceiling_pct": agg["overrun_ceiling_pct"],
        "exposure_m":          agg["exposure_m"],
        "rag_count":           agg["rag_count"],
    }
    # Keep Jan takeaway as placeholder for synthetic periods (LLM not re-run)

    # --- 03 Schedule Health ---
    sh = jsons["03_schedule_health.json"]["schedule_health"]
    sh["header"]["active_projects"] = agg["active"]
    sh["chart"] = {
        "on_track":      agg["on_track"],
        "delayed_small": agg["delayed_lt20"],
        "delayed_big":   agg["delayed_gt20"],
        "no_baseline":   agg["no_baseline"],
    }

    # --- 04 Budget Health ---
    bh = jsons["04_budget_health.json"]["budget_health"]
    bh["donut"] = agg["donut"]
    bh["header"]["subtitle"] = f"FY{agg['year']} Budget Distribution by investment category and key budget health indicators"

    # --- 06 Projects at Risk (top 5) ---
    ar = jsons["06_projects_at_risk.json"]["at_risk"]
    top5 = []
    for r in agg["rag_rows_ranked"][:5]:
        top5.append({
            "rag":            RAG_DECODE.get(r.get("rag_code"), r.get("rag_code")),
            "project":        r.get("DESCRIPTION") or "",
            "owner":          r.get("owner_name") or "-",
            "target_go_live": _date_format(parse_date(r.get("NEW_ANTICIPATED_COMPLETION_DATE"))),
            "cy_budget":      m(r.get("BUDGET_CY")),
            "progress_pct":   f"{int(f(r.get('EST_PERCENTAGE_OF_WORK_COMPLETED')))}%" if r.get("EST_PERCENTAGE_OF_WORK_COMPLETED") else "-",
            "highlights":     _highlights_template(r),
        })
    ar["top_n"]      = 5
    ar["exposure_m"] = agg["exposure_m"]
    ar["rag_count"]  = agg["rag_count"]
    ar["rows"]       = top5
    remaining = max(0, agg["rag_count"] - 5)
    ar["caption"]["remaining_count"]  = remaining
    ar["caption"]["total_rag"]        = agg["rag_count"]
    ar["caption"]["total_exposure_m"] = agg["exposure_m"]

    # --- 08 Appendix A.1 (full list) ---
    a1 = jsons["08_appendix_a1.json"]["appendix_a1"]
    projects = []
    for r in agg["rag_rows_a1"]:
        projects.append({
            "rag":        RAG_DECODE.get(r.get("rag_code"), r.get("rag_code")),
            "code":       r.get("REQUEST_CODE"),
            "project":    r.get("DESCRIPTION") or "",
            "owner":      r.get("owner_name") or "-",
            "go_live":    _date_format(parse_date(r.get("NEW_ANTICIPATED_COMPLETION_DATE"))),
            "budget":     m(r.get("BUDGET_CY")),
            "pct":        f"{int(f(r.get('EST_PERCENTAGE_OF_WORK_COMPLETED')))}%" if r.get("EST_PERCENTAGE_OF_WORK_COMPLETED") else "-",
            "highlights": _highlights_template(r),
        })
    a1["total_count"] = len(projects)
    a1["projects"]    = projects

    # --- 09 Appendix A.2 Timeline ---
    tl = jsons["09_appendix_a2.json"]["timeline"]
    win_y1, win_y2 = agg["year"] - 1, agg["year"]
    today_idx = (agg["year"] - win_y1) * 12 + (agg["period_dt"].month - 1)
    def _to_idx(d):
        if d is None: return None
        try: yy, mm = d.year, d.month
        except Exception: return None
        return max(0, min(23, (yy - win_y1) * 12 + (mm - 1)))
    timeline_rows = []
    for r in agg["rag_rows_a1"]:
        short = (r.get("DESCRIPTION") or "")[:24].rstrip()
        s_idx = _to_idx(parse_date(r.get("BASELINE_START_DATE"))) or 0
        e_idx = _to_idx(parse_date(r.get("NEW_ANTICIPATED_COMPLETION_DATE")) or parse_date(r.get("BASELINE_PLANNED_COMPLETION_DATE"))) or 23
        if e_idx < s_idx: e_idx = s_idx
        pct = r.get("EST_PERCENTAGE_OF_WORK_COMPLETED")
        timeline_rows.append({
            "project_short": short,
            "pct":           f"{int(f(pct))}%" if pct else "-",
            "rag":           RAG_DECODE.get(r.get("rag_code"), r.get("rag_code")),
            "start_idx":     int(s_idx),
            "end_idx":       int(e_idx),
        })
    tl["window"]["y1"] = win_y1
    tl["window"]["y2"] = win_y2
    tl["window"]["today_idx"] = today_idx
    tl["month_headers_2025"] = [f"J{str(win_y1)[-2:]}", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    tl["month_headers_2026"] = [f"J{str(win_y2)[-2:]}", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    tl["today_label"] = period_info["display"].split()[0][:3] + " " + str(agg["year"])
    tl["rows"] = timeline_rows


def _rel(p: Path) -> str:
    """Display path relative to BASE when possible, else just the path itself."""
    try:
        return str(p.relative_to(BASE))
    except ValueError:
        return str(p)


def render_period(period_code: str, rows_all: list[dict], lifetime: int) -> Path:
    """Build JSONs, invoke renderer, return path to produced PPTX."""
    info = PERIODS[period_code]
    print(f"\n— rendering {info['display']} ({period_code}) —")

    # Start from his Jan JSONs (full schema with all required fields)
    jsons: dict[str, dict] = {}
    for fname in sorted(HIS_JAN_JSONS.glob("*.json")):
        jsons[fname.name] = json.loads(fname.read_text(encoding="utf-8"))

    # Apply this period's meta + computed values
    patch_meta(jsons, info)
    agg = compute_per_period_aggregates(rows_all, period_code, lifetime)
    patch_data_fields(jsons, agg, info)

    # Write into the working renderer's values/ folder
    values_dir = WORKING / "values"
    for name, data in jsons.items():
        (values_dir / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote 9 per-slide JSONs to {_rel(values_dir)}")

    # Invoke his renderer with an explicit output path so we control the filename
    out_pptx = WORKING.parent / "_renderer_out" / info["filename"]
    out_pptx.parent.mkdir(parents=True, exist_ok=True)
    if out_pptx.exists(): out_pptx.unlink()

    res = subprocess.run(
        [sys.executable, "render.py", str(out_pptx)],
        cwd=str(WORKING),
        capture_output=True, text=True, encoding="utf-8",
    )
    if res.returncode != 0:
        print("  STDOUT:", res.stdout)
        print("  STDERR:", res.stderr)
        raise RuntimeError(f"renderer failed for {info['display']}")
    if not out_pptx.exists():
        raise RuntimeError(f"renderer reported success but {out_pptx} missing\n{res.stdout}")

    print(f"  rendered → {_rel(out_pptx)} ({out_pptx.stat().st_size:,} bytes)")
    return out_pptx


def _load_joined_rows() -> list[dict]:
    """Load the fact rows joined to dimensions (shared by main() and build_one())."""
    dims = load_dims()
    rows_all = load_csv("GOLD_fct_pcs_report.csv")
    join_dims(rows_all, dims)
    return rows_all


def _period_lifetimes(lifetime_jan: int) -> dict[str, int]:
    return {
        "202512": int(round(lifetime_jan * 0.88)),
        "202601": lifetime_jan,
        "202602": int(round(lifetime_jan * 1.08)),
    }


def build_one(period_code: str) -> Path:
    """Render a single period on demand and copy it to website/public/.
    Returns the path to the produced .pptx. Used by the live 'Generate' endpoint
    (scripts/serve_generate.py) so a click renders a fresh deck from the data.

    Renders in a fresh temp dir OUTSIDE OneDrive to avoid the file-lock that breaks
    rmtree on the in-repo working tree.
    """
    global WORKING
    if period_code not in PERIODS:
        raise ValueError(f"unknown period {period_code!r}")
    if not HIS_SPEC.exists():
        raise RuntimeError(f"renderer spec folder not found: {HIS_SPEC}")

    rows_all = _load_joined_rows()
    lifetimes = _period_lifetimes(lifetime_completed_count())
    present = {r["REF_PERIOD"] for r in rows_all if r.get("REF_PERIOD")}
    if period_code not in present:
        raise RuntimeError(
            f"period {period_code} not in source data (present: {sorted(present)})"
        )

    tmp_root = Path(tempfile.mkdtemp(prefix="piq_render_"))
    WORKING = tmp_root / "_renderer"          # render_period() reads this global
    try:
        shutil.copytree(HIS_SPEC, WORKING)    # fresh working copy in temp (no rmtree race)
        produced = render_period(period_code, rows_all, lifetimes.get(period_code))
        dest = PUBLIC / PERIODS[period_code]["filename"]
        if dest.exists():
            dest.unlink()
        shutil.copy2(produced, dest)
        return dest
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def main():
    if not HIS_SPEC.exists():
        sys.exit(f"ERROR: his spec folder not found: {HIS_SPEC}")
    import csv_to_jsons
    if csv_to_jsons.SOURCE == "fabric":
        print("Source: LIVE Fabric GOLD layer (OneLake Delta over HTTPS)")
    elif not (BASE / "data" / "csv" / "GOLD_fct_pcs_report.csv").exists():
        sys.exit("ERROR: data/csv/ not seeded. Run: python scripts/seed_csv.py")

    setup_working_copy()

    # Load CSV + dims, join, get lifetime count
    dims = load_dims()
    rows_all = load_csv("GOLD_fct_pcs_report.csv")
    join_dims(rows_all, dims)
    lifetime_jan = lifetime_completed_count()

    # Scale lifetime per period (Dec slightly fewer, Feb slightly more)
    period_lifetimes = {
        "202512": int(round(lifetime_jan * 0.88)),
        "202601": lifetime_jan,
        "202602": int(round(lifetime_jan * 1.08)),
    }

    # Only render periods that actually exist in the source data. Live Fabric
    # has just the real period(s) (e.g. 202601); the synthetic Dec/Feb demo
    # periods only exist in the CSV layer.
    present = {r["REF_PERIOD"] for r in rows_all if r.get("REF_PERIOD")}
    render_codes = [c for c in PERIODS if c in present]
    if not render_codes:
        sys.exit(f"ERROR: none of {list(PERIODS)} found in source data (present: {sorted(present)}).")

    rendered = []
    for period_code in render_codes:
        info = PERIODS[period_code]
        produced = render_period(period_code, rows_all,
                                 period_lifetimes.get(period_code, lifetime_jan))
        # Copy to website/public/
        dest = PUBLIC / info["filename"]
        if dest.exists(): dest.unlink()
        shutil.copy2(produced, dest)
        rendered.append(dest)
        print(f"  copied  → {dest.relative_to(BASE)}")

    print(f"\nDone. {len(rendered)} PPTXs in website/public/:")
    for p in rendered:
        print(f"  {p.name}  ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
