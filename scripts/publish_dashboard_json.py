# -*- coding: utf-8 -*-
"""publish_dashboard_json.py — push the dashboard JSON (and optionally the decks) to the
Azure Blob container the website reads from. This is the "Fabric pushes JSON" sink.

Pipeline (option D):
    Fabric (scheduled) → csv_to_jsons computes <ymd>.json + manifest.json from live GOLD
                       → publish_dashboard_json uploads them to a Blob container
    Website (PIQ_CONFIG.dataBaseUrl) reads manifest.json + <ymd>.json straight from Blob.
    No Fabric auth in the website's request path.

Run after csv_to_jsons has produced website/public/data/*.json:

    # auth: a connection string OR account + SAS token
    set AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=...;AccountKey=...;
    # or:  set AZURE_STORAGE_ACCOUNT=myacct  &  set AZURE_STORAGE_SAS=?sv=...
    set AZURE_BLOB_CONTAINER=portfolioiq

    python scripts/publish_dashboard_json.py            # upload JSON + manifest
    python scripts/publish_dashboard_json.py --decks    # also upload PortfolioIQ_*.pptx
    python scripts/publish_dashboard_json.py --dry-run   # show what would upload, no creds
    python scripts/publish_dashboard_json.py --set-cors  # one-time: allow the site origin

Then set the website's PIQ_CONFIG.dataBaseUrl to:
    https://<account>.blob.core.windows.net/<container>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "website" / "public" / "data"
PUBLIC = BASE / "website" / "public"

JSON_CT = "application/json"
PPTX_CT = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
# Short cache so a fresh publish shows up quickly; tune for your cadence.
CACHE = "public, max-age=300"


def _gather(decks: bool) -> list[tuple[Path, str, str]]:
    """Return (local_path, blob_name, content_type) for everything to upload."""
    items: list[tuple[Path, str, str]] = []
    if not DATA_DIR.exists():
        sys.exit(f"ERROR: {DATA_DIR} not found. Run csv_to_jsons first.")
    for p in sorted(DATA_DIR.glob("*.json")):
        items.append((p, p.name, JSON_CT))           # manifest.json + <ymd>.json
    if decks:
        for p in sorted(PUBLIC.glob("PortfolioIQ_*.pptx")):
            items.append((p, p.name, PPTX_CT))
    return items


def _container_client():
    """Build a ContainerClient from env. Supports connection string or account+SAS."""
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        sys.exit("ERROR: pip install azure-storage-blob")
    container = os.environ.get("AZURE_BLOB_CONTAINER", "portfolioiq")
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if conn:
        svc = BlobServiceClient.from_connection_string(conn)
    else:
        acct = os.environ.get("AZURE_STORAGE_ACCOUNT")
        sas = os.environ.get("AZURE_STORAGE_SAS")
        if not (acct and sas):
            sys.exit("ERROR: set AZURE_STORAGE_CONNECTION_STRING, or AZURE_STORAGE_ACCOUNT + AZURE_STORAGE_SAS")
        svc = BlobServiceClient(account_url=f"https://{acct}.blob.core.windows.net",
                                credential=sas if sas.startswith("?") else "?" + sas)
    cc = svc.get_container_client(container)
    try:
        cc.create_container()  # idempotent-ish; ignore if exists
    except Exception:
        pass
    return svc, cc, container


def set_cors(svc, origins: list[str]) -> None:
    from azure.storage.blob import CorsRule
    rule = CorsRule(allowed_origins=origins, allowed_methods=["GET", "HEAD", "OPTIONS"],
                    allowed_headers=["*"], exposed_headers=["*"], max_age_in_seconds=3600)
    svc.set_service_properties(cors=[rule])
    print(f"CORS set for origins: {origins}")


def main():
    args = set(sys.argv[1:])
    decks = "--decks" in args
    dry = "--dry-run" in args
    items = _gather(decks)

    print(f"{'DRY-RUN: ' if dry else ''}publishing {len(items)} file(s) from {DATA_DIR.relative_to(BASE)}"
          + (" + decks" if decks else ""))
    for p, name, ct in items:
        print(f"  {name:38} {ct.split('.')[-1]:5} {p.stat().st_size:>9,} B")
    if dry:
        print("dry-run only; no upload.")
        return

    from azure.storage.blob import ContentSettings
    svc, cc, container = _container_client()

    if "--set-cors" in args:
        origins = os.environ.get("PIQ_SITE_ORIGINS", "*").split(",")
        set_cors(svc, [o.strip() for o in origins])

    for p, name, ct in items:
        cc.upload_blob(name, p.read_bytes(), overwrite=True,
                       content_settings=ContentSettings(content_type=ct, cache_control=CACHE))
        print(f"  uploaded {name}")

    acct_host = svc.url.rstrip("/")
    print(f"\nDone. Point the website at:\n  dataBaseUrl: \"{acct_host}/{container}\"")


if __name__ == "__main__":
    main()
