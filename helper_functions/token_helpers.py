from dataclasses import dataclass
from typing import Optional, Dict, Any
import requests


# -----------------------------
# Types
# -----------------------------

@dataclass
class TestSettings:
    __test__ = False
    client_id: str
    client_secret: str
    tenant_id: str
    environment: str  # 'prod' | 'gov' | etc.


@dataclass
class ReportEmbedInfo:
    report_id: str
    workspace_id: str
    page_id: Optional[str] = None
    role: Optional[str] = None
    bookmark_id: Optional[str] = None


@dataclass
class APIEndpoints:
    api_prefix: str
    web_prefix: str


# -----------------------------
# Get Access Token (Service Principal)
# -----------------------------

def get_access_token(settings: TestSettings) -> str:
    url = f"https://login.microsoftonline.com/{settings.tenant_id}/oauth2/v2.0/token"

    data = {
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "grant_type": "client_credentials",
        "scope": "https://analysis.windows.net/powerbi/api/.default",
    }

    response = requests.post(url, data=data)
    response.raise_for_status()

    json_data = response.json()
    access_token = json_data.get("access_token")

    if not access_token:
        raise RuntimeError(f"Failed to get access token: {json_data}")

    return access_token


# -----------------------------
# Get Embed Token for a Report
# -----------------------------

def get_report_embed_token(
    report_info: ReportEmbedInfo,
    endpoints: APIEndpoints,
    access_token: str
) -> str:

    url = (
        f"{endpoints.api_prefix}/v1.0/myorg/groups/"
        f"{report_info.workspace_id}/reports/"
        f"{report_info.report_id}/GenerateToken"
    )

    body: Dict[str, Any] = {
        "accessLevel": "View"
    }

    if report_info.role:
        body["identities"] = [
            {
                "username": report_info.role,
                "roles": [report_info.role],
                "datasets": []
            }
        ]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    response = requests.post(url, json=body, headers=headers)
    response.raise_for_status()

    json_data = response.json()
    token = json_data.get("token")

    if not token:
        raise RuntimeError(
            f"Failed to get embed token for report "
            f"{report_info.report_id}: {json_data}"
        )

    return token


# -----------------------------
# Create Report Embed Info
# -----------------------------

def create_report_embed_info(report: Dict[str, Any]) -> ReportEmbedInfo:
    if not report.get("WorkspaceId"):
        raise ValueError(f"Report {report.get('Name')} is missing WorkspaceId")

    if not report.get("Id"):
        raise ValueError(f"Report {report.get('Name')} is missing reportId")

    pages = report.get("Pages") or []

    return ReportEmbedInfo(
        report_id=report["Id"],
        workspace_id=report["WorkspaceId"],
        page_id=pages[0] if pages else None,
        role=report.get("Role"),
        bookmark_id=report.get("BookmarkId"),
    )


# -----------------------------
# API Endpoints helper
# -----------------------------

def get_api_endpoints(environment: str) -> APIEndpoints:
    env = environment.lower()

    if env == "prod":
        return APIEndpoints(
            api_prefix="https://api.powerbi.com",
            web_prefix="https://app.powerbi.com"
        )

    if env == "gov":
        return APIEndpoints(
            api_prefix="https://api.powerbigov.us",
            web_prefix="https://app.powerbigov.us"
        )

    raise ValueError(f"Unknown environment: {environment}")
