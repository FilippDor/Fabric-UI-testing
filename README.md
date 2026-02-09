# Power BI Visual Regression Testing with CI/CD

> Automated CI/CD pipeline that tests every page of every Power BI report in a workspace for visual rendering errors — using Python, Playwright, and GitHub Actions.

---

## The Problem

Power BI reports can silently break — a DAX measure changes, a data source times out, a visual fails to render. Without automated testing, these issues go unnoticed until someone manually opens the report and spots the problem.

## The Solution

This project automates visual regression testing for an entire Power BI workspace. On every push or PR, a GitHub Actions pipeline:

1. Authenticates to Azure AD using a **Service Principal**
2. Discovers all reports in the workspace via the **Power BI REST API**
3. Generates embed tokens and loads each report in a **headless Chromium** browser
4. Iterates through **every page** of every report
5. Detects **visual rendering errors** via the Power BI JavaScript SDK
6. Captures **screenshots** of failed pages
7. Produces a **JSON + HTML report** with pass/fail status and render times

If any visual fails to render, the pipeline fails and the team is alerted.

---

## Architecture

```
                    GitHub Actions (CI/CD)
                            │
                            ▼
              ┌─────────────────────────────┐
              │   Service Principal Auth    │
              │   (Azure AD OAuth2)         │
              └──────────┬──────────────────┘
                         │ Access Token
                         ▼
              ┌─────────────────────────────┐
              │   Power BI REST API         │
              │   ├─ List workspace reports │
              │   └─ Generate embed tokens  │
              └──────────┬──────────────────┘
                         │ Embed Tokens
                         ▼
              ┌─────────────────────────────┐
              │   Playwright + Chromium     │
              │   ├─ Load Power BI JS SDK   │
              │   ├─ Embed each report      │
              │   ├─ Navigate all pages     │
              │   ├─ Monitor render events  │
              │   └─ Screenshot failures    │
              └──────────┬──────────────────┘
                         │
                         ▼
              ┌─────────────────────────────┐
              │   Test Artifacts            │
              │   ├─ HTML report            │
              │   ├─ JSON results + metrics │
              │   └─ Failure screenshots    │
              └─────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Test Framework** | Pytest with pytest-playwright, pytest-xdist (parallel) |
| **Browser Automation** | Playwright (headless Chromium) |
| **Power BI Integration** | Power BI JavaScript SDK + REST API |
| **Authentication** | MSAL (Azure AD Service Principal, OAuth2 client_credentials) |
| **CI/CD** | GitHub Actions |
| **Language** | Python 3.11+ |

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/visual-tests.yml`) runs on:
- Every **push** to `main`
- Every **pull request** to `main`
- **Manual trigger** (workflow_dispatch)

### Pipeline Steps

```yaml
Checkout → Python Setup → Install Deps → Install Chromium
    → Fetch Report Metadata → Run Visual Tests → Upload Artifacts
```

Test artifacts (HTML report, JSON results, screenshots) are uploaded and retained for 30 days.

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `SP_CLIENT_ID` | Service Principal Application (client) ID |
| `SP_TENANT_ID` | Azure AD Tenant ID |
| `SP_CLIENT_SECRET` | Service Principal client secret |
| `WORKSPACE_ID` | Power BI Workspace ID |
| `ENVIRONMENT` | `prod` or `gov` |
| `DEFAULT_RLS_ROLE` | Default RLS role for datasets with Row-Level Security |

---

## Row-Level Security (RLS) Handling

A key feature of this framework is **automatic RLS detection and handling**. Many Power BI datasets enforce Row-Level Security, which requires an effective identity (username + role) when generating embed tokens. This framework handles it transparently:

1. **Auto-detection** — The metadata fetcher queries each dataset via the Power BI REST API and reads the `isEffectiveIdentityRequired` and `isEffectiveIdentityRolesRequired` flags. These are stored in the metadata JSON so the test runner knows which datasets need an identity.

2. **Automatic token generation** — When a dataset requires RLS, the embed token request automatically includes an effective identity with the `DEFAULT_RLS_ROLE` defined in your environment. Datasets without RLS get a simple token with no identity.

3. **Per-report override** — You can set a `"Role"` field on any report in the metadata JSON to use a specific role instead of the default.

| Scenario | Behavior |
|----------|----------|
| Dataset has no RLS | No effective identity sent — works out of the box |
| Dataset has RLS | Effective identity with `DEFAULT_RLS_ROLE` from environment |
| Per-report override | Set `"Role"` field in `reports_datasets.json` |

This means you can test a workspace with a mix of RLS and non-RLS reports without any manual configuration beyond setting `DEFAULT_RLS_ROLE` once.

---

## What Gets Tested

For each report in the workspace:

| Test | Description |
|------|-------------|
| Configuration validation | Env vars, report metadata, unique IDs |
| Service Principal auth | OAuth2 token acquisition |
| Embed token generation | Per-report embed tokens via REST API |
| Visual rendering | Every page rendered in headless browser |
| Error detection | Power BI SDK visual errors captured |
| Performance metrics | Render time per page recorded |

---

## Setup & Local Development

### Prerequisites

- Python 3.11+
- A Power BI workspace with published reports
- An Azure AD Service Principal with **Contributor** access to the workspace ([setup guide](https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal))

### Install

```bash
git clone https://github.com/FilippDor/Fabric_CICD.git
cd Fabric_CICD

python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

pip install -r requirements_visual_test.txt
playwright install --with-deps chromium

cp .env.example .env
# Edit .env with your credentials
```

### Run

```bash
# Fetch report metadata from workspace
python -m helper_functions.get_workspace_reports_datasets

# Run tests
pytest

# Run tests in parallel
pytest -n auto
```

### Output

| Artifact | Location |
|----------|----------|
| HTML report | `tests/test-results/playwright_report.html` |
| JSON results | `tests/test-results/all_reports_results.json` |
| Failure screenshots | `tests/test-results/*.png` |

---

## Project Structure

```
├── .github/workflows/
│   └── visual-tests.yml                 # CI/CD pipeline
├── conftest.py                          # Pytest hooks — result aggregation
├── pytest.ini                           # Pytest configuration
├── requirements_visual_test.txt         # Dependencies
├── helper_functions/
│   ├── token_helpers.py                 # Service Principal auth & embed tokens
│   ├── get_workspace_reports_datasets.py  # Workspace report discovery
│   ├── file_reader.py                   # JSON utilities
│   └── log_utils.py                     # Logging
├── metadata/reports/
│   └── reports_datasets.json            # Auto-generated report metadata
└── tests/
    └── test_visual_render_embed_multiple_pics.py  # Visual regression tests
```
