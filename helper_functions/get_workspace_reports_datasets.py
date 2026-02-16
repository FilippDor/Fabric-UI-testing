#!/usr/bin/env python3
import os
import sys
import json
import requests
from datetime import datetime, timezone
from pathlib import Path


def fetch_workspace_metadata(
    client_id: str,
    client_secret: str,
    tenant_id: str,
    workspace_id: str,
    environment: str = "prod",
    output_path: Path | str | None = None,
) -> dict:
    """
    Fetch all reports and datasets from a Power BI workspace.

    Returns dict with keys: workspaceId, generatedAtUtc, reportCount, reports.
    If output_path is given, also writes JSON to that file.
    """
    env = environment.lower()

    # Environment URLs
    if env == "gov":
        auth_url = f"https://login.microsoftonline.us/{tenant_id}/oauth2/v2.0/token"
        scope = "https://analysis.usgovcloudapi.net/powerbi/api/.default"
        pbi_api = "https://api.powerbigov.us"
    else:
        auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        scope = "https://analysis.windows.net/powerbi/api/.default"
        pbi_api = "https://api.powerbi.com"

    # Token Acquisition
    token_resp = requests.post(
        auth_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
        timeout=30,
    )

    if token_resp.status_code != 200:
        raise RuntimeError(
            f"Failed to acquire access token: {token_resp.text}"
        )

    access_token = token_resp.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    # Fetch Reports
    reports_url = f"{pbi_api}/v1.0/myorg/groups/{workspace_id}/reports"
    resp = requests.get(reports_url, headers=headers, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch reports: {resp.text}")

    reports_raw = resp.json().get("value", [])

    # Deterministic ordering
    reports_raw.sort(key=lambda r: r["id"])

    # Fetch dataset details (including RLS roles)
    dataset_ids = {r.get("datasetId") for r in reports_raw if r.get("datasetId")}
    dataset_metadata = {}

    for ds_id in dataset_ids:
        try:
            ds_url = f"{pbi_api}/v1.0/myorg/groups/{workspace_id}/datasets/{ds_id}"
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
            "WorkspaceId": workspace_id,
            "IsEffectiveIdentityRequired": ds_info.get(
                "isEffectiveIdentityRequired", False
            ),
            "IsEffectiveIdentityRolesRequired": ds_info.get(
                "isEffectiveIdentityRolesRequired", False
            ),
        }
        report_list.append(report_entry)

    payload = {
        "workspaceId": workspace_id,
        "generatedAtUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        + "Z",
        "reportCount": len(report_list),
        "reports": report_list,
    }

    # Write output if path given
    if output_path is not None:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        tmp.replace(out)
        print(f"SUCCESS: Exported {payload['reportCount']} reports to {out}")

    return payload


# ------------------------------------
# Standalone script entry point
# ------------------------------------
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(".env")

    app_id = os.getenv("SP_CLIENT_ID")
    tenant_id = os.getenv("SP_TENANT_ID")
    client_secret = os.getenv("SP_CLIENT_SECRET")
    workspace_id = os.getenv("WORKSPACE_ID")
    environment = os.getenv("ENVIRONMENT", "prod")

    missing = [
        name
        for name, value in {
            "SP_CLIENT_ID": app_id,
            "SP_TENANT_ID": tenant_id,
            "SP_CLIENT_SECRET": client_secret,
            "WORKSPACE_ID": workspace_id,
        }.items()
        if not value
    ]

    if missing:
        print(
            f"ERROR: Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(2)

    base_dir = Path(__file__).resolve().parent.parent
    output_file = base_dir / "metadata" / "reports" / "reports_datasets.json"

    try:
        fetch_workspace_metadata(
            client_id=app_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            environment=environment,
            output_path=output_file,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(3)

    sys.exit(0)
