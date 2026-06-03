# Pipeline schema — per-slide contract

The PowerPoint template has **fixed slot counts** per slide. If the pipeline emits the wrong number of items, the deck renders broken (missing rows, blank cards, layout collapse). This document is the canonical contract that `csv_to_jsons.py` and `patch_period_pptxs.py` MUST honour.

## Hard counts (never deviate)

| Slide | Field | Required count | Rule when data is sparse |
|---|---|---|---|
| 1 Cover | `cover.*` | All required fields | (constants — never sparse) |
| 2 Snapshot | `tiles` (the 5 KPI tiles) | **5** | Always populate from `summary` (total, completed, overdue, budget, ytd) |
| 2 Snapshot | `takeaway` paragraphs | **3** | Verdict + Detail + Action. Pad with "Steady state" if insufficient data. |
| 3 Schedule | `schedule_chart` (bar values) | **4** | On Track / Delayed ≤20% / Delayed >20% / No Baseline — zero-fill if no rows |
| 3 Schedule | `schedule_bullets` | **3** | Risk bullets. Pad with neutral statements if fewer triggers fire. |
| 3 Schedule | `schedule_action` | **1** | `{text, owner, target}` — always emit, fallback to "Maintain monitoring" |
| 4 Budget | `budget_donut` (segments) | **4** | The 4 fixed Deloitte categories, zero-fill missing ones |
| 4 Budget | `budget_insights` | **4** | One per: within-budget · overrun-risk · exposure · dominant-category |
| 5 Decisions | `decision_cards` | **4** | Severity order **MUST be**: Critical → High → Medium → Low (D1/D2/D3/D4). Pad with low-severity "monitor" if fewer real items. |
| 6 At-risk | `at_risk_top5` | **5** | Top-5 by RAG-then-budget. Pad with empty rows if fewer flagged. |
| 7 Risks | `key_risks` | **3** (target) — **4** acceptable max | 3 by default; allow 4 for high-risk periods. Pad with "Watch" entries if needed. |
| 8 Appendix | `at_risk_full` | Variable (0–N) | Table capacity = 13 rows in template. Truncate at 13 max; blank trailing rows. |
| 9 Timeline | `timeline_rows` | Variable (0–N) | Same — 13 rows max capacity. |

## Slot field schemas

### `takeaway` — slide 2 (3 paragraphs, in order)
```json
["verdict sentence (≤80 chars)",
 "detail sentence (1-2 sentences with numbers)",
 "imperative action sentence starting with 'Immediate action required:' or 'Continue...'"]
```

### `schedule_bullets` — slide 3 (exactly 3)
```json
["bullet 1: most-delayed quantification",
 "bullet 2: baseline-coverage gap",
 "bullet 3: headline % in plain words"]
```

### `budget_insights` — slide 4 (exactly 4, in order)
```json
[
  {"bold": "<bold lead clause>", "tail": " <regular tail starting with space>"},
  // 4 items: within-budget · overrun-risk · exposure · dominant-category
]
```

### `decision_cards` — slide 5 (exactly 4, in order CRITICAL → HIGH → MEDIUM → LOW)
```json
[
  {"code": "D1", "severity": "CRITICAL", "title": "...", "hero": "...", "context": "...", "owner": "...", "target": "..."},
  {"code": "D2", "severity": "HIGH",     ...},
  {"code": "D3", "severity": "MEDIUM",   ...},
  {"code": "D4", "severity": "LOW",      ...}
]
```

### `key_risks` — slide 7 (3 or 4)
```json
[
  {"type": "I"|"R", "description": "...", "severity": "HIGH"|"MED"|"LOW",
   "status": "Identified"|"In Control"|"Mitigated"|"Closed",
   "mitigation": "...", "owner": "...", "target": "Mon YYYY"}
]
```

### `at_risk_top5` — slide 6 (exactly 5 rows, header excluded)
```json
[
  {"rag": "Red"|"Amber", "project": "...", "owner": "...", "go_live": "...",
   "budget": "€XXk"|"€X.XM", "pct": "N%", "highlights": "one-line action"}
]
```

## Content sources by tier

For every field above, the pipeline picks ONE of:

1. **DERIVED** — computed from `data/csv/GOLD_fct_pcs_report.csv` (deterministic, free, instant)
2. **TEMPLATED** — text patterns built from DERIVED values (deterministic, free, instant). Default for narrative when LLM disabled.
3. **LLM (Claude Haiku 4.5)** — when `ANTHROPIC_API_KEY` is set in env. Generates narrative for `takeaway` / `schedule_bullets` / `budget_insights` / `decision_cards` / `key_risks`. Cached per period in JSON output.
4. **CONSTANT** — brand text, never per-period. Hardcoded.

## Count-enforcement contract (Python)

`csv_to_jsons.py` MUST run this validation before writing any per-period JSON:

```python
REQUIRED_COUNTS = {
    "tiles":            5,
    "schedule_chart":   4,
    "budget_donut":     4,
    "takeaway":         3,
    "schedule_bullets": 3,
    "budget_insights":  4,
    "decision_cards":   4,
    "at_risk_top5":     5,
}

def validate(out):
    for key, n in REQUIRED_COUNTS.items():
        actual = len(out.get(key, []))
        assert actual == n, f"{key} requires exactly {n}, got {actual}"
    # key_risks tolerated as 3 or 4
    n_risks = len(out.get("key_risks", []))
    assert n_risks in (3, 4), f"key_risks requires 3-4, got {n_risks}"
```

If validation fails, the script raises and no JSON is written — better to fail loudly than emit a broken deck.

## Refresh workflow with the contract

```powershell
cd 03_enerwave_portfolio_reporting_agent

# 1. (Optional) Set Claude key for real narrative — else templated fallback runs
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 2. Run pipeline (enforces counts, emits structured JSON)
python scripts/csv_to_jsons.py

# 3. Rebuild + patch PPTXs (consumes structured JSON)
python scripts/build_period_pptxs.py
python scripts/patch_period_pptxs.py
```

If `ANTHROPIC_API_KEY` is unset, the pipeline runs without errors using templates. The decks render correctly either way because COUNTS are enforced upstream.

## Why this contract matters

Without strict counts:
- Emit 3 cards on slide 5 → 4th card placeholder remains as Jan content → mixed-period deck
- Emit 5 budget insights → only 4 fit → 5th silently dropped, layout odd
- Emit 0 takeaway paragraphs → slide 2 missing the whole right-rail block

With the contract:
- Every slide always gets exactly the right number of items
- LLM and template paths produce identical-shape output
- Deck renders correctly in PowerPoint every time
