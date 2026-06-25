# Option D — Fabric publishes the dashboard JSON

The website reads its data from a store that **Fabric writes to on a schedule**. No Fabric
auth sits in the website's request path — the browser just fetches static JSON from Blob.

```
Fabric (scheduled notebook)                         Azure Blob (public read + CORS)        Website
───────────────────────────                         ──────────────────────────────        ───────
NB_PUBLISH_DASHBOARD_JSON
  ├─ csv_to_jsons (live GOLD over OneLake)  ──►  manifest.json
  │     + AI narrative (Claude)                  <ymd>.json            ──► fetch(dataBaseUrl/manifest.json)
  └─ publish_dashboard_json (upload)             [PortfolioIQ_*.pptx]      fetch(dataBaseUrl/<ymd>.json)
```

## One-time setup

1. **Create a Blob container** (e.g. `portfolioiq`) on an Azure Storage account.
   - Allow anonymous **read** on blobs (or front it with a CDN), so the static site can GET them.
2. **CORS**: allow the site origin. Either run the notebook with `--set-cors` (uses
   `PIQ_SITE_ORIGINS`), or:
   ```
   az storage cors add --services b --methods GET HEAD OPTIONS \
     --origins https://portfolioiq-eight.vercel.app --allowed-headers '*' \
     --max-age 3600 --account-name <account>
   ```
3. **Point the website at the store** — in [website/config.js](../website/config.js):
   ```js
   dataBaseUrl: "https://<account>.blob.core.windows.net/portfolioiq"
   ```
   Leave it blank to keep reading the bundled `public/data/` (the default/fallback).

## The producer (in Fabric)

- Upload the repo's `scripts/` to `Files/portfolioiq/scripts` (one-time), or `git clone` it
  in a first cell.
- Open **[NB_PUBLISH_DASHBOARD_JSON.py](NB_PUBLISH_DASHBOARD_JSON.py)** as a Fabric notebook,
  set the parameter cell (Blob connection string / container, `ANTHROPIC_API_KEY` for the
  narrative), and run.
- **Schedule** it from a Fabric **Data Pipeline** (nightly, or trigger at month-end close).

## Running the publisher anywhere (CI / local)

`csv_to_jsons` reads live GOLD and writes `website/public/data/*.json`; then:

```powershell
$env:AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=...;AccountKey=...;"
$env:AZURE_BLOB_CONTAINER = "portfolioiq"
python scripts/csv_to_jsons.py                 # compute from live Fabric
python scripts/publish_dashboard_json.py --decks --set-cors   # push JSON (+ decks) to Blob
```

`--dry-run` lists what would upload without credentials. Cache-Control is 300s, so a fresh
publish appears within ~5 minutes; tune in [publish_dashboard_json.py](../scripts/publish_dashboard_json.py).

## Why D

- **No Fabric auth in the request path** — the site only reads static JSON from Blob/CDN, so
  it works on the static Vercel host with no secrets and no per-request latency.
- **Fresh by schedule** — data is as of the last Fabric run; the cadence is yours to set.
- **Same JSON everywhere** — dashboard, the live `Generate` deck, and downloads all read the
  one published snapshot, so they can never disagree.
