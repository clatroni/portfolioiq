"""seed_csv.py — bootstrap the working multi-period CSV with a deliberate story arc.

Copies the original GOLD CSVs from input/Archive/.../csv results/ into
data/csv/, then APPENDS synthetic rows for Dec 2025 + Feb 2026 to
GOLD_fct_pcs_report.csv. Same shape Fabric would export after 3 pipeline runs.

The synthesis is deliberate: specific REQUEST_CODEs move between RAG / status
states across periods so the dashboard tells a coherent story:

    Dec 2025  -> Jan 2026:  +3 new flags emerge (10 -> 13 flagged)
                            Steam Turbine Inspection surfaces as Amber (€4.5M)
                            3D HRSG Scanning, TIL Auto Tune newly flagged
                            YTD spend kicks off (1 month -> 4 months cumulative)

    Jan 2026  -> Feb 2026:  Same flag COUNT (13) but +€3.3M more exposure
                            Strategic spare parts resolved (closeout, off list)
                            ST Hydraulic Pumps de-escalated (Red -> Amber)
                            Desuperheaters completed (90% -> done)
                            Steam Turbine Generator rewinding emerges (€3M Amber)
                            DERMS emerges (€265k Amber)

Workflow:
  1. python scripts/seed_csv.py        ← creates data/csv/ from scratch
  2. python scripts/csv_to_jsons.py    ← reads data/csv/, emits per-period JSONs
  3. When Fabric real data lands: replace data/csv/GOLD_fct_pcs_report.csv,
     re-run csv_to_jsons. Synthetic transitions silently retire.

Use --force to overwrite an existing multi-period file.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from copy import deepcopy
from pathlib import Path

BASE       = Path(__file__).resolve().parent.parent
SOURCE_CSV = BASE / "input" / "Archive" / "inputs" / "02 Fabric Results in csv format" / "csv results"
WORK_CSV   = BASE / "data" / "csv"

FILES_TO_COPY = [
    "GOLD_fct_pcs_report.csv",
    "GOLD_project_high_level_status.csv",
    "GOLD_dim_general_status_rag.csv",
    "GOLD_dim_project_owner.csv",
    "GOLD_dim_project_category.csv",
    "GOLD_dim_active_projects_schedule_health_kpi.csv",
    "GOLD_dim_active_projects_budget_status_kpi.csv",
]

# RAG IDs (from dim_general_status_rag.csv): 13=Amber, 14=Green, 15=Red

# ───────────────────────────────────────────────────────────────────────────────
# DECEMBER 2025  (the "before" snapshot — 1 month earlier than real Jan)
# ───────────────────────────────────────────────────────────────────────────────
DEC_2025 = {
    "display":   "December 2025",
    "scale_ytd": 0.20,   # 1 month into FY (vs ~4 months for Jan)

    # These projects were GREEN in Dec but became flagged in Jan.
    # (3 projects emerge as new flags Dec -> Jan = main story driver)
    "set_rag_green": [
        "2025-00159",   # 3D HRSG Scanning (became Red in Jan — 0% progress)
        "2025-00127",   # Steam Turbine Major Inspection (Amber, €4.5M — big new exposure)
        "2025-00164",   # TIL001121 Auto Tune System (Amber, €500k)
    ],

    # These projects were ACTIVE in Dec but PROJECT_COMPLETED=1 in Jan.
    # (3 projects closed out Dec -> Jan, so in Dec they were still active)
    "uncomplete": [
        "2025-00040",   # myElpedison Redesign (100% complete with €0 in Jan = closeout)
        "2025-00095",   # Strategic spare parts (similar pattern)
        # 3rd one picked dynamically (first other PROJECT_COMPLETED=1 row not above)
    ],

    # These projects were PENDING (PROJECT_ACTIVE=0) in Dec but became active in Jan.
    # (4 newly activated projects bumped Dec's active count from 96 -> 100 in Jan)
    "deactivate": [
        "2025-00170",   # Digitalization of Forms and Flows
        "2025-00150",   # Ultrasonic flow meter
        "2025-00045",   # Strategic Clients Portal
        "2025-00128",   # Steam Turbine Generator rewinding (3M, became Amber in Feb)
    ],
}

# ───────────────────────────────────────────────────────────────────────────────
# FEBRUARY 2026  (the "after" snapshot — 1 month later than real Jan)
# ───────────────────────────────────────────────────────────────────────────────
FEB_2026 = {
    "display":   "February 2026",
    "scale_ytd": 1.55,   # 5 months cumulative spend (vs 4 for Jan)

    # These Red/Amber projects were resolved in Feb (Green + Completed = off list).
    "resolved": [
        "2025-00095",   # Strategic spare parts: closeout — RAG to Green, mark completed
    ],

    # These Red projects de-escalated to Amber (still flagged but improving).
    "red_to_amber": [
        "2025-00144",   # ST Hydraulic Pumps Replacement (escalation worked)
    ],

    # These active projects completed in Feb (off active count, were Amber).
    "newly_completed": [
        "2025-00117",   # Desuperheaters replacement (90% in Jan -> done in Feb)
    ],

    # These projects newly flagged as Amber in Feb (emerging risk).
    "set_rag_amber": [
        "2025-00128",   # Steam Turbine Generator complete rewinding (€3M — big new exposure)
        "2025-00067",   # DERMS (€265k)
    ],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────
def f(s):
    try: return float(s)
    except: return 0.0

def synthesize_dec(base_rows: list[dict]) -> tuple[list[dict], list[str]]:
    rows = deepcopy(base_rows)
    log = [f"### December 2025 (REF_PERIOD=202512)",
           f"Generated from Jan 2026 baseline by reversing 1 month of portfolio progression.",
           f""]

    cfg = DEC_2025
    for r in rows:
        r["REF_PERIOD"] = "202512"

    # 1) Scale YTD spend (1 month into FY)
    for r in rows:
        v = f(r.get("ACTUAL_CUMULATIVE_KE"))
        if v > 0:
            r["ACTUAL_CUMULATIVE_KE"] = str(round(v * cfg["scale_ytd"], 2))
    log.append(f"- **Scaled YTD spend** × {cfg['scale_ytd']:.2f} (1 month vs 4 months cumulative)")

    # 2) Set explicit projects back to Green (they became flagged in Jan)
    by_code = {r["REQUEST_CODE"]: r for r in rows}
    for code in cfg["set_rag_green"]:
        if code in by_code:
            r = by_code[code]
            old = r["GENERAL_STATUS_RAG_ID"]
            r["GENERAL_STATUS_RAG_ID"] = "14"
            log.append(f"- **{code}** {r['DESCRIPTION'][:50]}: RAG_ID {old} → 14 (Green) — became flagged in Jan")

    # 3) Revert completions (3 projects completed in Jan were still active in Dec)
    explicit_uncomplete = list(cfg["uncomplete"])
    flipped = []
    for code in explicit_uncomplete:
        if code in by_code and by_code[code]["PROJECT_COMPLETED"] == "1":
            by_code[code]["PROJECT_COMPLETED"] = "0"
            by_code[code]["PROJECT_ACTIVE"] = "1"
            flipped.append(code)
    # Top up to 3 with any other completed (so Dec lifetime completed = Jan - 3)
    target = 3
    if len(flipped) < target:
        for r in rows:
            if len(flipped) >= target: break
            if r["PROJECT_COMPLETED"] == "1" and r["REQUEST_CODE"] not in flipped:
                r["PROJECT_COMPLETED"] = "0"
                r["PROJECT_ACTIVE"] = "1"
                flipped.append(r["REQUEST_CODE"])
    log.append(f"- **{len(flipped)} completions reverted** (active in Dec, completed in Jan): {', '.join(flipped)}")

    # 4) Deactivate 4 specific projects (they were pending in Dec, became active in Jan)
    flipped = []
    for code in cfg["deactivate"]:
        if code in by_code and by_code[code]["PROJECT_ACTIVE"] == "1":
            by_code[code]["PROJECT_ACTIVE"] = "0"
            flipped.append(code)
    log.append(f"- **{len(flipped)} active projects rolled back to pending** (newly activated in Jan): {', '.join(flipped)}")

    log.append("")
    return rows, log

def synthesize_feb(base_rows: list[dict]) -> tuple[list[dict], list[str]]:
    rows = deepcopy(base_rows)
    log = [f"### February 2026 (REF_PERIOD=202602)",
           f"Generated from Jan 2026 baseline by projecting 1 month of portfolio progression.",
           f""]

    cfg = FEB_2026
    for r in rows:
        r["REF_PERIOD"] = "202602"

    # 1) Scale YTD spend (5 months cumulative)
    for r in rows:
        v = f(r.get("ACTUAL_CUMULATIVE_KE"))
        if v > 0:
            r["ACTUAL_CUMULATIVE_KE"] = str(round(v * cfg["scale_ytd"], 2))
    log.append(f"- **Scaled YTD spend** × {cfg['scale_ytd']:.2f} (5 months vs 4)")

    by_code = {r["REQUEST_CODE"]: r for r in rows}

    # 2) Resolved (Red/Amber in Jan → Green + Completed in Feb, off the list)
    for code in cfg["resolved"]:
        if code in by_code:
            r = by_code[code]
            r["GENERAL_STATUS_RAG_ID"] = "14"
            r["PROJECT_COMPLETED"] = "1"
            r["PROJECT_ACTIVE"] = "0"
            log.append(f"- **{code}** {r['DESCRIPTION'][:50]}: resolved — Red→Green + marked completed")

    # 3) Red → Amber (de-escalation)
    for code in cfg["red_to_amber"]:
        if code in by_code:
            r = by_code[code]
            old = r["GENERAL_STATUS_RAG_ID"]
            r["GENERAL_STATUS_RAG_ID"] = "13"
            log.append(f"- **{code}** {r['DESCRIPTION'][:50]}: de-escalated Red→Amber (still flagged)")

    # 4) Active → Completed in Feb (clean closeout: also flip RAG to Green so it leaves the at-risk list)
    for code in cfg["newly_completed"]:
        if code in by_code:
            r = by_code[code]
            r["PROJECT_COMPLETED"] = "1"
            r["PROJECT_ACTIVE"] = "0"
            r["GENERAL_STATUS_RAG_ID"] = "14"
            log.append(f"- **{code}** {r['DESCRIPTION'][:50]}: completed in Feb (was Amber, 90% in Jan) — closeout to Green")

    # 5) Green → Amber (new flags emerging — the headline Feb story)
    for code in cfg["set_rag_amber"]:
        if code in by_code:
            r = by_code[code]
            r["GENERAL_STATUS_RAG_ID"] = "13"
            log.append(f"- **{code}** {r['DESCRIPTION'][:50]}: NEW Amber flag (€{f(r['BUDGET_CY'])/1000:.0f}k budget)")

    log.append("")
    return rows, log


def existing_periods(fpath: Path) -> set[str]:
    if not fpath.exists(): return set()
    with open(fpath, encoding="utf-8") as f:
        return {r["REF_PERIOD"] for r in csv.DictReader(f) if r.get("REF_PERIOD")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Overwrite data/csv/ even if it already has multi-period data")
    args = ap.parse_args()

    if not SOURCE_CSV.exists():
        sys.exit(f"ERROR: source folder not found: {SOURCE_CSV}")

    WORK_CSV.mkdir(parents=True, exist_ok=True)
    fct_target = WORK_CSV / "GOLD_fct_pcs_report.csv"

    existing = existing_periods(fct_target)
    if len(existing) > 1 and not args.force:
        print(f"data/csv/GOLD_fct_pcs_report.csv already has {len(existing)} periods: {sorted(existing)}")
        print("Refusing to overwrite. Pass --force to rebuild from scratch.")
        sys.exit(0)

    print(f"Seeding {WORK_CSV} from {SOURCE_CSV} ...")
    for fname in FILES_TO_COPY:
        shutil.copy2(SOURCE_CSV / fname, WORK_CSV / fname)
        print(f"  copied {fname}")

    with open(fct_target, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        base = [r for r in reader if r["REF_PERIOD"] == "202601"]
    print(f"  base: {len(base)} real rows for REF_PERIOD=202601 (Jan 2026)")

    all_logs: list[str] = ["# Synthesis log — `data/csv/GOLD_fct_pcs_report.csv`",
                            "",
                            "Real Jan 2026 rows were copied unchanged from "
                            "`input/Archive/inputs/02 Fabric Results in csv format/csv results/`.",
                            "Synthetic Dec 2025 and Feb 2026 rows were derived by applying the "
                            "deliberate transitions documented below, so the period selector tells "
                            "a coherent month-over-month story.",
                            "",
                            "When real Fabric exports become available for these months, replace "
                            "`GOLD_fct_pcs_report.csv` here and re-run `csv_to_jsons.py`.",
                            "",
                            "---", ""]

    dec_rows, dec_log = synthesize_dec(base)
    feb_rows, feb_log = synthesize_feb(base)
    all_logs.extend(dec_log)
    all_logs.extend(feb_log)

    new_rows = dec_rows + feb_rows
    with open(fct_target, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        for r in new_rows:
            writer.writerow(r)
    print(f"  appended {len(new_rows)} synthetic rows (Dec 2025 + Feb 2026)")

    final = existing_periods(fct_target)
    print(f"  final periods in file: {sorted(final)}")

    (WORK_CSV / "_synthesis_log.md").write_text("\n".join(all_logs), encoding="utf-8")
    print(f"  wrote _synthesis_log.md (audit trail)")
    print("Done. Now run: python scripts/csv_to_jsons.py")


if __name__ == "__main__":
    main()
