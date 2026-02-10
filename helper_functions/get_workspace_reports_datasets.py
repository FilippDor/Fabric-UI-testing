#!/usr/bin/env python3
import os
import sys
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv


load_dotenv(".env")
BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------
# Configuration (env only)

APP_ID = os.getenv("SP_CLIENT_ID")
TENANT_ID = os.getenv("SP_TENANT_ID")
CLIENT_SECRET = os.getenv("SP_CLIENT_SECRET")
WORKSPACE_ID = os.getenv("WORKSPACE_ID")
ENVIRONMENT = os.getenv("ENVIRONMENT", "prod").lower()
OUTPUT_FILE = BASE_DIR / "metadata" / "reports" / "reports_datasets.json"

# -----------------------------
# Validation

missing = [
    name
    for name, value in {
        "SP_CLIENT_ID": APP_ID,
        "SP_TENANT_ID": TENANT_ID,
        "SP_CLIENT_SECRET": CLIENT_SECRET,
        "WORKSPACE_ID": WORKSPACE_ID,
    }.items()
    if not value
]

if missing:
    print(
        f"ERROR: Missing required environment variables: {', '.join(missing)}",
        file=sys.stderr,
    )
    sys.exit(2)

# -----------------------------
# Environment URLs

if ENVIRONMENT == "gov":
    AUTH_URL = f"https://login.microsoftonline.us/{TENANT_ID}/oauth2/v2.0/token"
    SCOPE = "https://analysis.usgovcloudapi.net/powerbi/api/.default"
    PBI_API = "https://api.powerbigov.us"
else:
    AUTH_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    SCOPE = "https://analysis.windows.net/powerbi/api/.default"
    PBI_API = "https://api.powerbi.com"

# -----------------------------
# Token Acquisition

token_resp = requests.post(
    AUTH_URL,
    data={
        "grant_type": "client_credentials",
        "client_id": APP_ID,
        "client_secret": CLIENT_SECRET,
        "scope": SCOPE,
    },
    timeout=30,
)

if token_resp.status_code != 200:
    print("ERROR: Failed to acquire access token", file=sys.stderr)
    print(token_resp.text, file=sys.stderr)
    sys.exit(3)

access_token = token_resp.json()["access_token"]

headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json",
}

# -----------------------------
# Fetch Reports

reports_url = f"{PBI_API}/v1.0/myorg/groups/{WORKSPACE_ID}/reports"
resp = requests.get(reports_url, headers=headers, timeout=30)

if resp.status_code != 200:
    print("ERROR: Failed to fetch reports", file=sys.stderr)
    print(resp.text, file=sys.stderr)
    sys.exit(4)

reports_raw = resp.json().get("value", [])

# -----------------------------
# Deterministic ordering

reports_raw.sort(key=lambda r: r["id"])

# -----------------------------
# Fetch dataset details (including RLS roles)

dataset_ids = {r.get("datasetId") for r in reports_raw if r.get("datasetId")}
dataset_metadata = {}

for ds_id in dataset_ids:
    try:
        ds_url = f"{PBI_API}/v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{ds_id}"
        ds_resp = requests.get(ds_url, headers=headers, timeout=30)
        if ds_resp.ok:
            ds_data = ds_resp.json()
            ds_name = ds_data.get("name", "")
            is_effective_identity_required = ds_data.get(
                "isEffectiveIdentityRequired", False
            )
            is_effective_identity_roles_required = ds_data.get(
                "isEffectiveIdentityRolesRequired", False
            )

            dataset_metadata[ds_id] = {
                "name": ds_name,
                "isEffectiveIdentityRequired": is_effective_identity_required,
                "isEffectiveIdentityRolesRequired": is_effective_identity_roles_required,
            }
            print(
                f"  Dataset {ds_id} ({ds_name}): effectiveIdentityRequired={is_effective_identity_required}, rolesRequired={is_effective_identity_roles_required}"
            )
    except Exception as e:
        print(f"  WARN: Could not fetch dataset {ds_id}: {e}", file=sys.stderr)

# -----------------------------
# Build payload

report_list = []
for r in reports_raw:
    ds_id = r.get("datasetId")
    ds_info = dataset_metadata.get(ds_id, {})
    report_entry = {
        "Id": r["id"],
        "Name": r["name"],
        "WebUrl": r.get("webUrl"),
        "EmbedUrl": r.get("embedUrl"),
        "DatasetId": ds_id,
        "DatasetName": ds_info.get("name", ""),
        "WorkspaceId": WORKSPACE_ID,
        "IsEffectiveIdentityRequired": ds_info.get(
            "isEffectiveIdentityRequired", False
        ),
        "IsEffectiveIdentityRolesRequired": ds_info.get(
            "isEffectiveIdentityRolesRequired", False
        ),
    }
    report_list.append(report_entry)

payload = {
    "workspaceId": WORKSPACE_ID,
    "generatedAtUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    + "Z",
    "reportCount": len(report_list),
    "reports": report_list,
}

# -----------------------------
# Write output atomically

output_path = Path(OUTPUT_FILE).resolve()
output_path.parent.mkdir(parents=True, exist_ok=True)
tmp_path = output_path.with_suffix(".tmp")

with tmp_path.open("w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)

tmp_path.replace(output_path)

# -----------------------------
# Machine-friendly success output

print(f"SUCCESS: Exported {payload['reportCount']} reports to {output_path}")

sys.exit(0)
