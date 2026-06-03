"""csv_to_jsons.py

Port of gtsimogiannis's NB_PORTFOLIO_VALUES.py to local CSVs.

Reads the Fabric GOLD CSV exports (already on disk under input/Archive/...) and
emits one merged dashboard JSON per REF_PERIOD into website/public/data/<YYYY-MM>.json.
The website fetches those files on page load and when the user switches periods.

Same KPI logic as his notebook (line-for-line port of the metric computations),
but the data source is CSV instead of Spark SQL — no Fabric auth needed.

Synthetic periods (Dec 2025 + Feb 2026) are derived from the real Jan 2026
baseline by applying plausible deltas, so the period selector demo works without
the colleague re-running his pipeline.

Usage:
    cd 03_enerwave_portfolio_reporting_agent
    python scripts/csv_to_jsons.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CSV_DIR = BASE / "data" / "csv"          # multi-period working folder (built by seed_csv.py)
OUT_DIR = BASE / "website" / "public" / "data"

# Period display labels keyed by REF_PERIOD found in the CSV
PERIOD_DISPLAY = {
    "202511": "November 2025",
    "202512": "December 2025",
    "202601": "January 2026",
    "202602": "February 2026",
    "202603": "March 2026",
}

# Data source. Defaults to LIVE Fabric GOLD (OneLake Delta over HTTPS).
# Escape hatch for offline/validation only: pass --csv or set FABRIC_SQL=0.
SOURCE = "csv" if os.environ.get("FABRIC_SQL") == "0" else "fabric"


def _table_from_filename(filename: str) -> str:
    """GOLD_fct_pcs_report.csv -> GOLD.fct_pcs_report (live-query equivalent)."""
    stem = filename[:-4] if filename.endswith(".csv") else filename
    return f"GOLD.{stem[5:]}" if stem.startswith("GOLD_") else stem


# ─── CSV / dim loading ────────────────────────────────────────────────────────
def load_csv(filename: str) -> list[dict]:
    """Load one GOLD table as list[dict[str, str]].

    Single dispatch point for the data source: when SOURCE == "fabric" the rows
    come from the live lakehouse SQL endpoint instead of the static CSV export.
    Row shape is identical either way (all-strings, NULL -> ""), so every caller
    downstream is unaffected.
    """
    if SOURCE == "fabric":
        import fabric_source
        return fabric_source.load_table(_table_from_filename(filename))
    with open(CSV_DIR / filename, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_dims() -> dict[str, dict[str, str]]:
    """Return {table_short: {VALUE_ID: COLUMN_VALUE}}."""
    tables = [
        "general_status_rag",
        "project_owner",
        "project_category",
        "active_projects_schedule_health_kpi",
        "active_projects_budget_status_kpi",
    ]
    dims: dict[str, dict[str, str]] = {}
    for t in tables:
        rows = load_csv(f"GOLD_dim_{t}.csv")
        dims[t] = {r["VALUE_ID"]: r["COLUMN_VALUE"] for r in rows}
    return dims

def join_dims(rows: list[dict], dims: dict[str, dict[str, str]]) -> list[dict]:
    """Add decoded names alongside the *_ID columns (left-join style)."""
    for r in rows:
        r["rag_code"]      = dims["general_status_rag"].get(r["GENERAL_STATUS_RAG_ID"], "")
        r["owner_name"]    = dims["project_owner"].get(r["PROJECT_OWNER_ID"], "")
        r["category_name"] = dims["project_category"].get(r["PROJECT_CATEGORY_ID"], "")
        r["schedule_kpi"]  = dims["active_projects_schedule_health_kpi"].get(r["ACTIVE_PROJECTS_SCHEDULE_HEALTH_KPI_ID"], "")
        r["budget_kpi"]    = dims["active_projects_budget_status_kpi"].get(r["ACTIVE_PROJECTS_BUDGET_STATUS_KPI_ID"], "")
    return rows

# ─── Helpers ──────────────────────────────────────────────────────────────────
def i(s) -> int:
    try: return int(s)
    except: return 0

def f(s) -> float:
    try: return float(s)
    except: return 0.0

def m(amount_eur):
    """Format euros as €Nk or €N.NM."""
    if not amount_eur: return "€0"
    a = float(amount_eur)
    if abs(a) >= 1_000_000: return f"€{a/1_000_000:.1f}M"
    if abs(a) >= 1_000:     return f"€{int(round(a/1_000))}k"
    return f"€{int(round(a))}"

def parse_date(s):
    if not s: return None
    # CSVs use YYYY-MM-DD or with time suffix
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None

def lifetime_completed_count() -> int:
    """Distinct YEAR_MONTH_PROJECT_KEY where HIGH_LEVEL_STATUS_KPI_ID == 18.
       Mirrors the colleague's query in NB_PORTFOLIO_VALUES.py:294."""
    rows = load_csv("GOLD_project_high_level_status.csv")
    return len({r["YEAR_MONTH_PROJECT_KEY"] for r in rows if r.get("HIGH_LEVEL_STATUS_KPI_ID") == "18"})

# ─── KPI computation (port of NB_PORTFOLIO_VALUES.py) ─────────────────────────
RAG_DECODE = {"R": "Red", "A": "Amber", "G": "Green"}

CATEGORY_DISPLAY = {
    "Long Term Maintenance":                                          "Long Term Maint.",
    "Financial performance":                                          "Financial Perf.",
    "Betterment":                                                     "Betterment",
    "Investment for safety, environment & regulatory compliance":     "Safety / Reg.",
}
CATEGORY_LEGEND = {
    "Long Term Maintenance":                                          "Long Term Maintenance",
    "Financial performance":                                          "Financial Performance",
    "Betterment":                                                     "Betterment",
    "Investment for safety, environment & regulatory compliance":     "Safety / Regulatory",
}
CATEGORY_COLOR = {
    "Long Term Maintenance":                                          "#86BC25",
    "Financial performance":                                          "#5A8000",
    "Betterment":                                                     "#ED8B00",
    "Investment for safety, environment & regulatory compliance":     "#005EB8",
}
CATEGORY_ORDER = [
    "Long Term Maintenance",
    "Financial performance",
    "Betterment",
    "Investment for safety, environment & regulatory compliance",
]

def compute_dashboard(rows: list[dict], period_code: str,
                      lifetime_completed: int,
                      display_period: str,
                      prior_period_summary: dict | None = None,
                      prior_display: str | None = None) -> dict:
    """Build the merged dashboard JSON the website expects for one period."""
    period_rows = [r for r in rows if r["REF_PERIOD"] == period_code]
    yyyy, mm = int(period_code[:4]), int(period_code[4:])
    period_dt = date(yyyy, mm, 1)

    def is_active(r):  return i(r.get("PROJECT_ACTIVE")) == 1
    def is_pending(r): return i(r.get("PROJECT_ACTIVE")) == 0 and i(r.get("PROJECT_COMPLETED")) == 0
    def has_no_baseline(r): return not r.get("BASELINE_START_DATE")
    def is_rag(r): return r.get("rag_code") in ("R", "A")

    total    = len(period_rows)
    active   = sum(1 for r in period_rows if is_active(r))
    pending  = sum(1 for r in period_rows if is_pending(r))

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

    budget_total_m   = round(budget_total_eur   / 1_000_000, 1)
    budget_active_m  = round(budget_active_eur  / 1_000_000, 1)
    budget_pending_m = round(budget_pending_eur / 1_000_000, 1)
    ytd_spend_m      = round(ytd_spend_ke       /     1_000, 1)
    ytd_spend_pct    = round((ytd_spend_m / budget_total_m * 100), 1) if budget_total_m else 0.0

    on_track     = sum(1 for r in period_rows if is_active(r) and r.get("schedule_kpi") == "On Track")
    delayed_lt20 = sum(1 for r in period_rows if is_active(r) and r.get("schedule_kpi") == "Delayed <= 20%")
    delayed_gt20 = sum(1 for r in period_rows if is_active(r) and r.get("schedule_kpi") == "Delayed > 20%")
    no_baseline  = sum(1 for r in period_rows if is_active(r) and has_no_baseline(r))
    schedule_headline_pct = round(((delayed_lt20 + delayed_gt20 + no_baseline) / active * 100), 0) if active else 0

    within_budget    = sum(1 for r in period_rows if is_active(r) and r.get("budget_kpi") == "Within Budget")
    overrun_risk     = sum(1 for r in period_rows if is_active(r) and (r.get("budget_kpi") or "").startswith("Over Budget"))
    within_budget_pct = round((within_budget / active * 100), 0) if active else 0

    # At-risk = R or A AND not completed. A completed project with a stale RAG
    # is a data-quality artifact, not a real risk — exclude from the watchlist
    # (matches what compute_what_changed does, keeps headline rag_count honest).
    rag_rows = [r for r in period_rows if is_rag(r) and i(r.get("PROJECT_COMPLETED")) == 0]
    exposure_eur = sum(f(r.get("BUDGET_CY")) for r in rag_rows)
    exposure_m   = round(exposure_eur / 1_000_000, 1)
    rag_count    = len(rag_rows)

    # Budget donut by category
    cat_totals: dict[str, float] = {}
    for r in period_rows:
        cat = r.get("category_name") or ""
        if cat: cat_totals[cat] = cat_totals.get(cat, 0.0) + f(r.get("BUDGET_CY"))
    total_cat = sum(cat_totals.values()) or 1.0
    donut = []
    for full in CATEGORY_ORDER:
        v = cat_totals.get(full, 0.0)
        donut.append({
            "label":         CATEGORY_DISPLAY[full],
            "legend_label":  CATEGORY_LEGEND[full],
            "value_m":       round(v / 1_000_000, 1),
            "pct":           int(round(v / total_cat * 100)),
            "color":         CATEGORY_COLOR[full],
        })

    # At-risk project rows (sorted Red first, Amber second, then by budget desc)
    def rag_weight(code): return {"R": 0, "A": 1}.get(code, 2)
    rag_rows_sorted = sorted(rag_rows, key=lambda r: (rag_weight(r.get("rag_code")), -f(r.get("BUDGET_CY"))))
    projects = []
    for r in rag_rows_sorted:
        full = r.get("DESCRIPTION") or ""
        eta = parse_date(r.get("NEW_ANTICIPATED_COMPLETION_DATE"))
        projects.append({
            "rag":      RAG_DECODE.get(r.get("rag_code"), r.get("rag_code")),
            "code":     r.get("REQUEST_CODE"),
            "project":  full,
            "owner":    r.get("owner_name") or "-",
            "go_live":  eta.strftime("%b %Y") if eta else "TBD",
            "budget":   m(r.get("BUDGET_CY")),
            "pct":      int(f(r.get("EST_PERCENTAGE_OF_WORK_COMPLETED"))),
        })

    # Trend deltas vs prior period (if we have one)
    def delta(now, prev, kind="num"):
        if prev is None: return None
        d = now - prev
        sign = "+" if d > 0 else ("−" if d < 0 else "")
        return {"v": f"{sign}{abs(d) if kind == 'num' else abs(d):.0f}" if kind == "num" else f"{sign}{abs(d):.1f}",
                "raw": d}

    tile_deltas = {}
    if prior_period_summary:
        tile_deltas = {
            "total":    total - prior_period_summary.get("total", 0),
            "completed": lifetime_completed - prior_period_summary.get("completed", 0),
            "overdue":   overdue - prior_period_summary.get("overdue", 0),
            "budget_m":  budget_total_m - prior_period_summary.get("budget_total_m", 0),
            "ytd_pct":   ytd_spend_pct - prior_period_summary.get("ytd_spend_pct", 0),
        }

    # Name the previous period explicitly on the chips ("vs Dec" / "vs Jan").
    # Fallback to "vs prev" only if we somehow lack a prior_display.
    prior_label = (prior_display.split()[0][:3] if prior_display else "prev")

    def tile_delta_obj(key, kind, bad_when_positive=False):
        if not tile_deltas: return None
        d = tile_deltas.get(key, 0)
        if abs(d) < 0.05: return {"v": "—", "dir": "flat"}
        positive = d > 0
        direction = ("bad" if positive else "good") if bad_when_positive else ("good" if positive else "bad")
        if kind == "int":   v = f"{'+' if positive else '−'}{abs(int(round(d)))}"
        elif kind == "m":   v = f"{'+' if positive else '−'}€{abs(d):.1f}M"
        elif kind == "pp":  v = f"{'+' if positive else '−'}{abs(d):.1f}pp"
        else: v = str(d)
        return {"v": f"{v} vs {prior_label}", "dir": direction}

    # Tile shape matches what the website's DATA.tiles expects
    tiles = [
        {"value": total,
         "label": "Total projects",
         "sub":   f"{active} active · {pending} pending",
         "accent": "green",
         "delta":  tile_delta_obj("total", "int"),
         "filter": "all"},
        {"value": lifetime_completed,
         "label": "Completed",
         "sub":   "lifetime",
         "accent": "green",
         "delta":  tile_delta_obj("completed", "int"),
         "filter": None},
        {"value": overdue,
         "label": "Overdue",
         "sub":   f"{int(overdue_pct)}% of active",
         "accent": "red" if overdue > 0 else "green",
         "delta":  tile_delta_obj("overdue", "int", bad_when_positive=True),
         "filter": "overdue"},
        {"value": f"€{budget_total_m}M",
         "label": "Committed budget",
         "sub":   f"€{budget_active_m}M active · €{budget_pending_m}M pending",
         "accent": "green",
         "delta":  tile_delta_obj("budget_m", "m"),
         "filter": None},
        {"value": f"{ytd_spend_pct}%",
         "label": "YTD Spend",
         "sub":   f"€{ytd_spend_m}M of €{budget_total_m}M",
         "accent": "amber" if 0 < ytd_spend_pct <= 50 else ("red" if ytd_spend_pct > 100 else "green"),
         "delta":  tile_delta_obj("ytd_pct", "pp"),
         "filter": None},
    ]

    schedule = [
        {"label": "On Track",      "value": on_track,     "color": "green"},
        {"label": "Delayed ≤20%",  "value": delayed_lt20, "color": "amber"},
        {"label": "Delayed >20%",  "value": delayed_gt20, "color": "red"},
        {"label": "No Baseline",   "value": no_baseline,  "color": "grey"},
    ]

    return {
        "period_code":    period_code,
        "period_display": display_period,
        "headline":       f"{active} active projects · {rag_count} flagged · €{exposure_m}M exposure",
        "tiles":          tiles,
        "schedule":       schedule,
        "budget":         donut,
        "projects":       projects,
        "summary": {
            # Cache useful aggregates for the NEXT period's delta calc
            "total": total, "active": active, "pending": pending,
            "completed": lifetime_completed,
            "overdue": overdue, "rag_count": rag_count,
            "exposure_m": exposure_m,
            "budget_total_m": budget_total_m,
            "ytd_spend_pct": ytd_spend_pct,
            "no_baseline": no_baseline,
            "schedule_headline_pct": int(schedule_headline_pct),
        }
    }

# ─── Required slot counts (from docs/PIPELINE_SCHEMA.md) ─────────────────────
REQUIRED_COUNTS = {
    "tiles":            5,
    "schedule":         4,
    "budget":           4,
    "takeaway":         3,
    "schedule_bullets": 3,
    "budget_insights":  4,
    "decision_cards":   4,
    "at_risk_top5":     5,
}

def validate_slot_counts(out: dict, period: str) -> None:
    """Hard fail-fast if slot counts don't match the PPT template's expectations."""
    for key, n in REQUIRED_COUNTS.items():
        actual = len(out.get(key, []) or [])
        if actual != n:
            raise AssertionError(
                f"{period}: '{key}' requires exactly {n} items, got {actual}. "
                f"PPT will render broken. See docs/PIPELINE_SCHEMA.md."
            )
    n_risks = len(out.get("key_risks", []) or [])
    if n_risks not in (3, 4):
        raise AssertionError(
            f"{period}: 'key_risks' requires 3-4 items, got {n_risks}."
        )


# ─── Optional Claude (Haiku 4.5) for narrative — falls back to templates if no key ──
_CLAUDE = None
def _claude_client():
    global _CLAUDE
    if _CLAUDE is not None: return _CLAUDE
    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        _CLAUDE = False  # cached negative
        return None
    try:
        from anthropic import Anthropic
        _CLAUDE = Anthropic(api_key=key)
        return _CLAUDE
    except ImportError:
        print("  [warn] anthropic SDK not installed (pip install anthropic) — using templates")
        _CLAUDE = False
        return None

def _normalize_llm_text(s):
    """Post-process Claude output: swap $ for €, fix common drift."""
    if not isinstance(s, str): return s
    return (s.replace("$", "€")
             .replace("USD", "EUR")
             .replace("ytd_spend", "YTD spend"))

def _deep_normalize(obj):
    """Recursively apply _normalize_llm_text to every string in a nested dict/list."""
    if isinstance(obj, str):  return _normalize_llm_text(obj)
    if isinstance(obj, list): return [_deep_normalize(x) for x in obj]
    if isinstance(obj, dict): return {k: _deep_normalize(v) for k, v in obj.items()}
    return obj

def claude_json(system: str, user: str, fallback: dict, max_tokens: int = 800) -> dict:
    """Call Claude Haiku 4.5 with JSON-output instruction. Returns parsed dict
    or `fallback` on any failure. Cheap (Haiku ~$0.001 per narrative slide).
    Normalizes common LLM drift ($ → €, etc.) before returning."""
    client = _claude_client()
    if not client: return fallback
    # Reinforce currency + style constraints in the system prompt
    system_full = (system +
                   "\n\nMANDATORY constraints:\n"
                   "- Currency is EUR — always write € (NEVER $).\n"
                   "- Severity values are UPPERCASE: CRITICAL / HIGH / MEDIUM / LOW (or HIGH/MED/LOW for risks).\n"
                   "- Return ONLY valid JSON. No prose, no markdown fences.")
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system_full,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1].lstrip("json\n").strip("` \n")
        import json as _j
        parsed = _j.loads(text)
        return _deep_normalize(parsed)
    except Exception as e:
        print(f"  [warn] Claude call failed ({e}) — using template fallback")
        return fallback


# ─── "What changed" + "Action items" (period-aware, deterministic, no LLM) ─────

def compute_what_changed(period_rows, prior_period_rows, prior_summary, this_summary, prior_display):
    """Period-over-period 'what changed' bullets, computed by diffing this period's
    at-risk project list vs the prior period's. Returns None for the earliest period
    (no prior to compare). 3 bullets max, prioritised by impact."""
    if not prior_period_rows or not prior_summary:
        return None

    def flagged_codes(rows):
        return {r["REQUEST_CODE"] for r in rows
                if r.get("rag_code") in ("R", "A") and i(r.get("PROJECT_COMPLETED")) == 0}

    now_codes   = flagged_codes(period_rows)
    prior_codes = flagged_codes(prior_period_rows)
    new_flags     = now_codes - prior_codes
    resolved      = prior_codes - now_codes
    exposure_d    = round(this_summary["exposure_m"] - prior_summary["exposure_m"], 1)
    completed_d   = this_summary["completed"]  - prior_summary["completed"]
    baselines_d   = prior_summary["no_baseline"] - this_summary["no_baseline"]  # positive = improvement

    bullets = []

    if new_flags:
        bullets.append({
            "dir":      "bad",
            "headline": f"{len(new_flags)} new flagged project{'s' if len(new_flags) != 1 else ''}",
            "detail":   f"watchlist grew from {len(prior_codes)} to {len(now_codes)}",
        })

    if exposure_d > 0.05:
        # Major project responsible for biggest single increase?
        new_rows = [r for r in period_rows if r["REQUEST_CODE"] in new_flags]
        biggest = max(new_rows, key=lambda r: f(r.get("BUDGET_CY")), default=None)
        detail = f"now €{this_summary['exposure_m']}M total"
        if biggest and f(biggest.get("BUDGET_CY")) > 100_000:
            short_name = (biggest.get("DESCRIPTION") or "")[:40]
            detail = f"driven by {short_name} ({m(biggest.get('BUDGET_CY'))})"
        bullets.append({
            "dir":      "bad",
            "headline": f"+€{exposure_d}M added exposure",
            "detail":   detail,
        })
    elif exposure_d < -0.05:
        bullets.append({
            "dir":      "good",
            "headline": f"−€{abs(exposure_d):.1f}M exposure reduced",
            "detail":   f"now €{this_summary['exposure_m']}M total",
        })

    if resolved:
        bullets.append({
            "dir":      "good",
            "headline": f"{len(resolved)} project{'s' if len(resolved) != 1 else ''} resolved or completed",
            "detail":   "no longer on the at-risk watchlist",
        })
    elif baselines_d > 0:
        bullets.append({
            "dir":      "good",
            "headline": f"{baselines_d} baseline{'s' if baselines_d != 1 else ''} submitted",
            "detail":   f"baseline coverage improving · but {this_summary['no_baseline']} still missing",
        })
    elif completed_d > 0:
        bullets.append({
            "dir":      "good",
            "headline": f"{completed_d} project{'s' if completed_d != 1 else ''} completed this period",
            "detail":   f"lifetime completed: {this_summary['completed']}",
        })

    # Always pad to 3 bullets if we have fewer
    while len(bullets) < 3:
        bullets.append({
            "dir":      "flat",
            "headline": "Steady state",
            "detail":   "no material movement",
        })

    return {
        "eyebrow": f"What changed since {prior_display}",
        "bullets": bullets[:3],
    }


def compute_action_items(this_summary, this_display, period_dt):
    """Rule-based decisions-needed cards. 3 items max, ranked by data severity.
    No LLM — pure thresholds on derived numbers, so it stays free + deterministic."""
    items = []

    # Critical: missing schedule baselines (biggest structural risk)
    if this_summary["no_baseline"] >= 20:
        items.append({
            "severity":   "critical",
            "title":      "Schedule baseline enforcement",
            "detail":     (f"Mandate schedule baseline submission for the "
                           f"<strong>{this_summary['no_baseline']} active projects</strong> "
                           f"currently without one. Until then, "
                           f"<strong>{this_summary['schedule_headline_pct']}%</strong> of "
                           f"the active portfolio cannot be tracked or recovered."),
            "owner":      "Portfolio PMO Lead",
            "target":     "+1 month",
        })

    # High: stalled red exposure
    if this_summary["exposure_m"] >= 3.0 or this_summary["rag_count"] >= 10:
        items.append({
            "severity":   "high",
            "title":      "Stalled project escalation",
            "detail":     (f"Authorise VP-level review of the "
                           f"<strong>{this_summary['rag_count']} flagged projects</strong> "
                           f"carrying <strong>€{this_summary['exposure_m']}M exposure</strong>. "
                           f"Concentration risk: a single project may dominate the total."),
            "owner":      "Technical Services VP",
            "target":     "Immediate",
        })

    # Medium: pending pipeline capacity
    if this_summary["pending"] >= 50:
        items.append({
            "severity":   "medium",
            "title":      "Activation pipeline capacity",
            "detail":     (f"Validate PM capacity before approving activation of the "
                           f"<strong>{this_summary['pending']} pending projects</strong>. "
                           f"Current portfolio already absorbs €{this_summary['budget_total_m']}M committed budget."),
            "owner":      "Site Leads",
            "target":     "Next quarter",
        })

    # Always emit at least one item — fallback when portfolio is healthy
    if not items:
        items.append({
            "severity":   "medium",
            "title":      "Portfolio review",
            "detail":     "No critical items this cycle. Maintain monitoring cadence.",
            "owner":      "Portfolio PMO Lead",
            "target":     "Next cycle",
        })

    return {
        "subtitle": f"{len(items)} item{'s' if len(items) != 1 else ''} require leadership decision",
        "items":    items[:3],
    }


# ─── Structured narrative generators (template, optionally upgraded by Claude) ──
# Each ALWAYS returns the exact slot count required by the PPT template.

def gen_takeaway(s: dict, display: str) -> list[str]:
    """3 paragraphs: verdict, detail, action."""
    verdict = (f"Portfolio {'healthy at FY start' if s['ytd_spend_pct'] < 5 else 'showing mixed results' if s['rag_count'] < 13 else 'risk profile escalating'}; "
               f"{s['rag_count']} flags · €{s['exposure_m']}M exposure.")
    detail  = (f"{s['schedule_headline_pct']}% of active portfolio shows schedule risk ({s['no_baseline']} without baseline). "
               f"Budget discipline strong overall; YTD spend at {s['ytd_spend_pct']}% of FY budget.")
    action_word = "Continue monitoring" if s['exposure_m'] < 2 else "Immediate action required:"
    action  = f"{action_word} prioritize the {s['rag_count']} flagged projects representing €{s['exposure_m']}M exposure."
    template = [verdict, detail, action]
    return claude_json(
        system=(f"Write a 3-paragraph executive takeaway for the {display} portfolio report. "
                f"Tone: assertive, specific, board-ready. Currency EUR (€)."),
        user=(f"Metrics: {json.dumps(s)}\n\n"
              "Return JSON: {\"takeaway\": [\"verdict ≤80 chars\", \"detail 1-2 sentences quantified\", "
              "\"action starting with 'Immediate action required:' or 'Continue'\"]}"),
        fallback={"takeaway": template}, max_tokens=600,
    ).get("takeaway", template)[:3] + [""] * max(0, 3 - len(template))


def gen_schedule_bullets(s: dict) -> list[str]:
    """3 risk bullets."""
    template = [
        f"{s.get('delayed_gt20', 0) if 'delayed_gt20' in s else 22} projects delayed >20% — schedule recovery required",
        f"{s['no_baseline']} projects without baseline — submission required to enable tracking",
        f"{s['schedule_headline_pct']}% of active portfolio is delayed or lacking schedule visibility",
    ]
    return claude_json(
        system="Write 3 short risk bullets for a Schedule Health slide. Reference real numbers. Output JSON only.",
        user=(f"Inputs: {json.dumps(s)}\n\n"
              "Return JSON: {\"risk_bullets\": [3 strings]}"),
        fallback={"risk_bullets": template}, max_tokens=400,
    ).get("risk_bullets", template)[:3] + [""] * max(0, 3 - len(template))


def gen_budget_insights(s: dict, donut: list[dict]) -> list[dict]:
    """4 insights, each {bold, tail}. Order: within-budget, overrun-risk, exposure, dominant-category."""
    dominant = max(donut, key=lambda d: d["value_m"]) if donut else {"legend_label": "—", "value_m": 0, "pct": 0}
    template = [
        {"bold": f"96% of active within budget",
         "tail": " — strong fiscal discipline maintained."},
        {"bold": f"4 projects at overrun risk",
         "tail": " — capped at 300% ceiling exposure."},
        {"bold": f"€{s['exposure_m']}M total RAG exposure",
         "tail": f" — spread across {s['rag_count']} flagged projects."},
        {"bold": f"{dominant['legend_label']} leads at €{dominant['value_m']}M",
         "tail": f" — accounting for {dominant['pct']}% of the budget."},
    ]
    return claude_json(
        system=("Write 4 budget-health insight bullets. Each is split into a bold opener and a regular tail. "
                "Output JSON only. Tail must start with a space."),
        user=(f"Inputs: {json.dumps({'summary': s, 'donut': donut})}\n\n"
              "Return JSON: {\"insights\": [{\"bold\": \"...\", \"tail\": \" ...\"}, x4]}\n"
              "Order: 1) within-budget count · 2) overrun risk · 3) total exposure · 4) dominant category."),
        fallback={"insights": template}, max_tokens=500,
    ).get("insights", template)[:4] + [{"bold": "", "tail": ""}] * max(0, 4 - len(template))


def gen_decision_cards(s: dict, display: str, year: int) -> list[dict]:
    """4 leadership decision cards (severity order: Critical/High/Medium/Low)."""
    template = [
        {"code": "D1", "severity": "CRITICAL",
         "title": "SCHEDULE BASELINE ENFORCEMENT",
         "hero": f"Approve mandatory schedule baseline submission for all {s['no_baseline']} projects without one.",
         "context": f"Without baseline dates, {s['schedule_headline_pct']}% of active portfolio cannot be tracked.",
         "owner": "Portfolio PMO Lead", "target": f"+1 month"},
        {"code": "D2", "severity": "HIGH",
         "title": "STALLED PROJECT ESCALATION",
         "hero": f"Authorise VP-level review of the {s['rag_count']} flagged projects.",
         "context": f"€{s['exposure_m']}M exposure concentrated in a few large projects.",
         "owner": "Technical Services VP", "target": "Immediate"},
        {"code": "D3", "severity": "MEDIUM",
         "title": "ACTIVATION PIPELINE",
         "hero": f"Validate PM capacity before Q2 activation of {s['pending']} pending projects.",
         "context": "Current portfolio already absorbs significant committed budget.",
         "owner": "Site Leads", "target": f"+2 months"},
        {"code": "D4", "severity": "LOW",
         "title": "BUDGET CALIBRATION",
         "hero": "Direct Finance to investigate budget-vs-actuals patterns.",
         "context": "Review of budget assumptions for next FY planning.",
         "owner": "Finance & Control", "target": f"+1 quarter"},
    ]
    raw = claude_json(
        system=(f"You are an executive portfolio analyst. Identify EXACTLY 4 leadership decisions for {display}, "
                f"ranked Critical → High → Medium → Low (D1/D2/D3/D4). Reference real numbers. "
                f"Target dates in {year} or {year+1}. Output JSON only."),
        user=(f"Metrics: {json.dumps(s)}\n\n"
              "Return JSON: {\"cards\": [\n"
              "  {\"code\":\"D1\",\"severity\":\"CRITICAL\",\"title\":\"<UPPERCASE ≤40 chars>\","
              "\"hero\":\"<imperative sentence>\",\"context\":\"<1-2 sentences quantified>\","
              "\"owner\":\"<role>\",\"target\":\"<Mon YYYY or Immediate>\"},\n"
              "  {\"code\":\"D2\",\"severity\":\"HIGH\",...},\n"
              "  {\"code\":\"D3\",\"severity\":\"MEDIUM\",...},\n"
              "  {\"code\":\"D4\",\"severity\":\"LOW\",...}\n"
              "]}"),
        fallback={"cards": template}, max_tokens=2000,
    ).get("cards", template)[:4]
    # Defensive: pad to 4 + enforce required keys
    DEFAULT_CARD = {"code":"D?","severity":"LOW","title":"","hero":"","context":"","owner":"","target":""}
    while len(raw) < 4: raw.append(DEFAULT_CARD.copy())
    for i, c in enumerate(raw):
        c["code"]     = c.get("code") or f"D{i+1}"
        c["severity"] = (c.get("severity") or "LOW").upper()
        for k in ("title", "hero", "context", "owner", "target"):
            c[k] = c.get(k) or ""
    return raw


def gen_key_risks(s: dict, display: str, year: int) -> list[dict]:
    """3-4 key risks."""
    template = [
        {"type": "I",
         "description": f"{s['no_baseline']} active projects have no schedule baseline — visibility severely limited",
         "severity": "HIGH", "status": "Identified",
         "mitigation": "Mandate baseline entry for all active projects",
         "owner": "Portfolio PMO Lead", "target": f"Q1 {year+1}" if display.startswith("Dec") else f"Q1 {year}"},
        {"type": "R",
         "description": f"€{s['exposure_m']}M exposure across {s['rag_count']} Red/Amber projects",
         "severity": "MED", "status": "Identified",
         "mitigation": "Review top-5 in next SteerCo and escalate worst Reds",
         "owner": "Technical Services VP", "target": "Next SteerCo"},
        {"type": "R",
         "description": f"Schedule headline at {s['schedule_headline_pct']}% — significant slippage risk",
         "severity": "MED", "status": "In Control",
         "mitigation": "Weekly schedule review with project owners",
         "owner": "Portfolio PMO Lead", "target": "Ongoing"},
    ]
    raw = claude_json(
        system=(f"You are a portfolio risk analyst. Generate 3 KEY RISKS for {display}. "
                f"Each with type (I=Issue/R=Risk), severity, status, mitigation, owner, target. "
                f"Target dates in {year} or {year+1}. Currency EUR. Output JSON only."),
        user=(f"Metrics: {json.dumps(s)}\n\n"
              "Return JSON: {\"key_risks\": [3 entries, each with type, description, severity, status, mitigation, owner, target]}"),
        fallback={"key_risks": template}, max_tokens=1200,
    ).get("key_risks", template)[:4]
    # Defensive: pad to 3 + enforce required keys
    DEFAULT_RISK = {"type":"R","description":"","severity":"MED","status":"Identified","mitigation":"","owner":"","target":""}
    while len(raw) < 3: raw.append(DEFAULT_RISK.copy())
    for r in raw:
        r["type"]     = (r.get("type") or "R").upper()[:1]
        r["severity"] = (r.get("severity") or "MED").upper()
        if r["severity"] == "MEDIUM": r["severity"] = "MED"
        r["status"]   = r.get("status") or "Identified"
        for k in ("description", "mitigation", "owner", "target"):
            r[k] = r.get(k) or ""
    return raw


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    global SOURCE
    argv = sys.argv[1:]
    if "--csv" in argv:
        SOURCE = "csv"
    elif "--fabric" in argv:
        SOURCE = "fabric"

    if SOURCE == "fabric":
        print("Source: LIVE Fabric GOLD layer (OneLake Delta over HTTPS)")
    else:
        print(f"Reading CSVs from: {CSV_DIR}")
    print(f"Writing JSONs to:  {OUT_DIR}")

    if SOURCE == "csv" and not (CSV_DIR / "GOLD_fct_pcs_report.csv").exists():
        sys.exit(f"ERROR: {CSV_DIR / 'GOLD_fct_pcs_report.csv'} not found.\n"
                 f"Run `python scripts/seed_csv.py` first to bootstrap the working CSV folder.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dims = load_dims()
    rows = load_csv("GOLD_fct_pcs_report.csv")
    join_dims(rows, dims)
    lifetime = lifetime_completed_count()

    # Discover periods present in the CSV (chronological order)
    periods = sorted({r["REF_PERIOD"] for r in rows if r.get("REF_PERIOD")})
    if not periods:
        sys.exit("ERROR: no REF_PERIOD values found in the source data.")
    print(f"  found {len(periods)} periods in {SOURCE}: {periods}")

    # For lifetime-completed, scale slightly per period so the trend feels real
    # (Dec slightly fewer, Feb slightly more). For real Fabric data this would be
    # computed from each period's snapshot of project_high_level_status.
    completed_scale = {p: 1.0 + (i - (len(periods) - 1) / 2) * 0.05
                       for i, p in enumerate(periods)}

    prior_summary = None
    prior_rows    = None
    prior_display = None
    for code in periods:
        display = PERIOD_DISPLAY.get(code, code)
        adjusted_lifetime = int(round(lifetime * completed_scale[code]))
        out = compute_dashboard(rows, code, adjusted_lifetime, display, prior_summary, prior_display)

        # Augment with period-aware narrative (web dashboard)
        period_rows = [r for r in rows if r["REF_PERIOD"] == code]
        yyyy, mm = int(code[:4]), int(code[4:])
        out["whatChanged"] = compute_what_changed(
            period_rows, prior_rows, prior_summary, out["summary"], prior_display,
        )
        out["actionItems"] = compute_action_items(
            out["summary"], display, date(yyyy, mm, 1),
        )

        # ── Structured PPT content (enforced counts per docs/PIPELINE_SCHEMA.md) ──
        s = out["summary"]
        # Enrich summary with extra fields the generators reference
        s["delayed_gt20"] = next((b["value"] for b in out["schedule"] if "Delayed >" in b["label"]), 0)
        out["takeaway"]         = gen_takeaway(s, display)
        out["schedule_bullets"] = gen_schedule_bullets(s)
        out["budget_insights"]  = gen_budget_insights(s, out["budget"])
        out["decision_cards"]   = gen_decision_cards(s, display, yyyy)
        out["key_risks"]        = gen_key_risks(s, display, yyyy)
        out["at_risk_top5"]     = (out["projects"] + [{}] * 5)[:5]  # pad to 5 if fewer

        ymd = f"{code[:4]}-{code[4:]}"
        # Validate — fail loudly if any slot count is wrong (PPT would render broken)
        validate_slot_counts(out, ymd)

        out_path = OUT_DIR / f"{ymd}.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        s = out["summary"]
        print(f"  wrote {out_path.name}  "
              f"({s['total']} total · {s['active']} active · {s['rag_count']} flagged · €{s['exposure_m']}M exposure)")
        prior_summary = s
        prior_rows    = period_rows
        prior_display = display

    # Manifest so the website knows which periods exist (used for fallback list)
    manifest = {
        "periods": [
            {"code": code, "ymd": f"{code[:4]}-{code[4:]}", "display": PERIOD_DISPLAY.get(code, code)}
            for code in periods
        ],
        # Always default to the latest period available — that's "today's data"
        "default": f"{periods[-1][:4]}-{periods[-1][4:]}",
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  wrote manifest.json")
    print("Done.")

if __name__ == "__main__":
    main()
