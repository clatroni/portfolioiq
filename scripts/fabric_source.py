"""fabric_source.py — live GOLD-layer reader for the Fabric lakehouse.

Drop-in replacement for the CSV reader in `csv_to_jsons.py`. Instead of reading
the static `data/csv/GOLD_*.csv` exports, it reads the live `GOLD` schema of
`LH_PORTFOLIO_MANAGEMENT` straight from OneLake as Delta tables, over HTTPS (443).

Why OneLake/Delta and not the SQL endpoint:
    The lakehouse SQL endpoint speaks TDS on port 1433, which the Deloitte
    corporate network blocks for all outbound Azure SQL. OneLake DFS is plain
    HTTPS on 443 (open), so we read the Delta tables directly with delta-rs.
    Same data, same rows — just a transport that gets through the firewall.

Auth: AAD token from the local `az` CLI — run `az login` once into the Deloitte
tenant before use. No secrets stored here.

Row shape matches `csv.DictReader`: every value is a string, NULL -> "". This is
deliberate — the KPI logic in csv_to_jsons.py assumes the all-strings convention
(e.g. `r["REF_PERIOD"] == "202601"`, `HIGH_LEVEL_STATUS_KPI_ID == "18"`), so the
downstream computation is byte-identical whether the source is CSV or Fabric.

Usage (smoke test):
    az login --allow-no-subscriptions --tenant <deloitte-tenant>
    python scripts/fabric_source.py
"""
from __future__ import annotations

import os
import subprocess
from decimal import Decimal

from deltalake import DeltaTable

# ─── Connection target (overridable by env) ───────────────────────────────────
# Per PROJECT_DOCUMENTATION.md §3 (Fabric items).
WORKSPACE_ID = os.environ.get("FABRIC_WORKSPACE_ID", "bdbe81c9-1aa3-442a-932b-08ebab8991d2")
LAKEHOUSE_ID = os.environ.get("FABRIC_LAKEHOUSE_ID", "63edf6fe-ceeb-4040-aa07-829024df4604")
SCHEMA       = os.environ.get("FABRIC_SQL_SCHEMA", "GOLD")

# OneLake DFS host + the AAD resource its tokens are minted for.
_ONELAKE_HOST = "onelake.dfs.fabric.microsoft.com"
_STORAGE_RESOURCE = "https://storage.azure.com/"


# ─── Auth ─────────────────────────────────────────────────────────────────────
_token_cache: dict[str, str] = {}


def _token() -> str:
    """AAD access token for the OneLake (storage) data plane, via `az`.

    On Windows `az` is a `.cmd` wrapper, so subprocess uses shell=True.
    """
    if _STORAGE_RESOURCE in _token_cache:
        return _token_cache[_STORAGE_RESOURCE]
    cmd = (f'az account get-access-token --resource "{_STORAGE_RESOURCE}" '
           f'--query accessToken -o tsv')
    try:
        raw = subprocess.check_output(cmd, shell=True, text=True).strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "Could not get an Azure access token. Run "
            "`az login --allow-no-subscriptions --tenant "
            "0435f515-1d02-4e55-9c28-bb4e32bd21d7` first."
        ) from e
    if not raw:
        raise RuntimeError("`az account get-access-token` returned empty — run `az login`.")
    _token_cache[_STORAGE_RESOURCE] = raw
    return raw


def _storage_options() -> dict:
    return {"bearer_token": _token(), "use_fabric_endpoint": "true"}


# ─── Value coercion (match csv.DictReader: all strings, NULL -> "") ───────────
def _stringify(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")   # 123.450000 -> '123.45'
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))                  # 202601.0 -> '202601' (keeps ID/period joins exact)
    return str(v)


# ─── Public API (mirrors csv_to_jsons.load_csv) ───────────────────────────────
def _table_uri(table: str) -> str:
    # table may be 'foo' or 'GOLD.foo'
    schema, _, name = table.partition(".") if "." in table else (SCHEMA, "", table)
    name = name or table
    return (f"abfss://{WORKSPACE_ID}@{_ONELAKE_HOST}/"
            f"{LAKEHOUSE_ID}/Tables/{schema}/{name}")


def load_table(table: str) -> list[dict]:
    """Read a GOLD Delta table as list[dict[str, str]]. `table` may be 'foo' or 'GOLD.foo'."""
    dt = DeltaTable(_table_uri(table), storage_options=_storage_options())
    rows = dt.to_pyarrow_table().to_pylist()
    return [{k: _stringify(v) for k, v in row.items()} for row in rows]


# Back-compat shim: csv_to_jsons.load_csv calls load_table; `query` kept for the
# odd ad-hoc caller. Full SQL isn't available over OneLake, so this supports the
# one DISTINCT-REF_PERIOD probe used in __main__ only.
def query(_sql: str) -> list[dict]:  # pragma: no cover - probe helper only
    raise NotImplementedError("Arbitrary SQL is unavailable over OneLake; use load_table().")


if __name__ == "__main__":
    print(f"Workspace: {WORKSPACE_ID}")
    print(f"Lakehouse: {LAKEHOUSE_ID}")
    print("Reading GOLD Delta tables from OneLake (HTTPS)…")
    for t in ("fct_pcs_report", "project_high_level_status",
              "dim_general_status_rag", "dim_project_owner",
              "dim_project_category",
              "dim_active_projects_schedule_health_kpi",
              "dim_active_projects_budget_status_kpi"):
        try:
            n = len(load_table(t))
            print(f"  GOLD.{t:<45} {n:>6} rows")
        except Exception as e:
            print(f"  GOLD.{t:<45} ERROR: {e}")
    try:
        fct = load_table("fct_pcs_report")
        periods = sorted({r["REF_PERIOD"] for r in fct if r.get("REF_PERIOD")})
        print("Periods live:", periods)
    except Exception as e:
        print("Periods: ERROR", e)
