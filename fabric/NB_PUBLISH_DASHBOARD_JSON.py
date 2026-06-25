# Fabric notebook: PUBLISH_DASHBOARD_JSON
# ----------------------------------------------------------------------------------------
# Computes the Portfolio IQ dashboard JSON from the live GOLD layer and PUSHES it to the
# Azure Blob container the website reads (option D — Fabric pushes JSON; no Fabric auth in
# the site's request path).
#
# Schedule this notebook from a Fabric Data Pipeline (e.g. nightly, or at month-end close).
# Paste each block below into its own notebook cell.
# ----------------------------------------------------------------------------------------

# CELL 1 — dependencies ------------------------------------------------------------------
# Fabric runtime already has pandas/pyspark. Add the publisher + narrative deps.
%pip install azure-storage-blob anthropic deltalake azure-identity

# CELL 2 — parameters (mark this cell as "Parameters" for the pipeline) ------------------
import os
# Where the repo's scripts/ live in the lakehouse. Upload the repo's scripts/ folder to
# Files/portfolioiq/scripts (one-time), or git-clone it in a prior cell.
SCRIPTS_PATH = "/lakehouse/default/Files/portfolioiq/scripts"
# Blob sink the website reads from (set these as pipeline parameters / Key Vault refs):
os.environ["AZURE_STORAGE_CONNECTION_STRING"] = ""   # or AZURE_STORAGE_ACCOUNT + _SAS
os.environ["AZURE_BLOB_CONTAINER"]            = "portfolioiq"
os.environ["PIQ_SITE_ORIGINS"]                = "https://portfolioiq-eight.vercel.app"
# Narrative is AI-written (Claude) inside csv_to_jsons — provide the key, or disable below.
os.environ["ANTHROPIC_API_KEY"]               = ""

# CELL 3 — make the repo scripts importable, force LIVE Fabric source --------------------
import sys
sys.path.insert(0, SCRIPTS_PATH)
import csv_to_jsons
csv_to_jsons.SOURCE = "fabric"   # read GOLD live over OneLake (default), not the CSV export

# CELL 4 — compute every period's JSON + manifest from live GOLD -------------------------
# Writes website/public/data/<ymd>.json + manifest.json under the repo path on the driver.
# (csv_to_jsons reads GOLD via fabric_source over OneLake using the notebook's identity.)
csv_to_jsons.main()

# CELL 5 — push the JSON (and optionally the rendered decks) to Blob ---------------------
import importlib, publish_dashboard_json
importlib.reload(publish_dashboard_json)
sys.argv = ["publish_dashboard_json.py", "--set-cors"]   # add "--decks" to also upload pptx
publish_dashboard_json.main()

# CELL 6 (optional) — also render + publish the decks live -------------------------------
# import render_live
# for ymd in ["2025-12", "2026-01", "2026-02"]:
#     render_live.build(ymd)
# sys.argv = ["publish_dashboard_json.py", "--decks"]; publish_dashboard_json.main()

# ----------------------------------------------------------------------------------------
# Result: manifest.json + <ymd>.json (+ optionally PortfolioIQ_*.pptx) land in the Blob
# container. Set the website's PIQ_CONFIG.dataBaseUrl to
#   https://<account>.blob.core.windows.net/portfolioiq
# and the dashboard reads fresh, Fabric-published data with no auth in its request path.
# ----------------------------------------------------------------------------------------
