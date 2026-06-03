# PortfolioIQ

An agentic portfolio-reporting solution that turns the **live Microsoft Fabric Gold layer**
into an executive status dashboard and an auto-generated PowerPoint deck.

## What it does

Reads the curated `GOLD` schema of the `LH_PORTFOLIO_MANAGEMENT` lakehouse directly from
**OneLake over HTTPS**, computes portfolio KPIs (schedule health, budget health, RAG
exposure, at-risk projects), and produces:

- a self-contained **web dashboard** (`website/`) for live demos, and
- a versioned **executive PPTX deck** (`scripts/render_decks.py`).

## Architecture

```
Fabric GOLD (LH_PORTFOLIO_MANAGEMENT)
   │  OneLake Delta over HTTPS (443)
   ▼
fabric_source.load_table()        ← scripts/fabric_source.py
   │
   ▼
csv_to_jsons.py  ── per-period dashboard JSON ──▶  website/public/data/<period>.json
   │
   ▼
render_decks.py  ── Jinja2 PPTX engine ──▶        website/public/PortfolioIQ_<period>.pptx
```

Data source is **live Fabric by default**. The CSV layer (`data/csv/`, `seed_csv.py`) is kept
only for offline/validation runs (`--csv` / `FABRIC_SQL=0`).

## Quick start

```powershell
# Auth once per session (Deloitte tenant — account has no subscription, Fabric only)
az login --allow-no-subscriptions --tenant 0435f515-1d02-4e55-9c28-bb4e32bd21d7

# Build the dashboard JSONs from live Fabric
python scripts/csv_to_jsons.py

# Render the executive deck from live Fabric
python scripts/render_decks.py

# Preview the site
cd website ; python -m http.server 8000   # → http://localhost:8000
```

## Layout

| Path | Purpose |
|---|---|
| `scripts/fabric_source.py` | Live GOLD reader (OneLake Delta) |
| `scripts/csv_to_jsons.py`  | KPI computation → per-period dashboard JSON |
| `scripts/render_decks.py`  | Executive PPTX renderer |
| `scripts/seed_csv.py`      | Offline/validation CSV seeding (not a live source) |
| `website/`                 | Static demo site (HTML/CSS/JS, no backend) |
| `data/csv/`                | Static GOLD exports — offline/validation only |
| `docs/`                    | Pipeline schema notes |

> **Data note:** this repository contains real portfolio data. Keep it **private**.
