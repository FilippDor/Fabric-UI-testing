# Power BI Visual Regression Testing with CI/CD

> Automated CI/CD pipeline that tests every page of every Power BI report in a workspace for visual rendering errors, using Python, Playwright, and GitHub Actions.

---

## The Problem

Power BI reports can silently break, a DAX measure changes, a data source times out, a visual fails to render. Without automated testing, these issues go unnoticed until someone manually opens the report and spots the problem.

## The Solution

This project automates visual regression testing for an entire Power BI workspace. On every push or PR, a GitHub Actions pipeline:

1. Authenticates to Azure AD using a **Service Principal**
2. Discovers all reports and datasets in the workspace via the **Power BI REST API**
3. Auto-detects **Row-Level Security** requirements per dataset
4. Generates embed tokens and loads each report in a **headless Chromium** browser
5. Iterates through **every page** of every report
6. Detects **visual rendering errors** via the Power BI JavaScript SDK
7. Captures **screenshots** of failed pages
8. Produces a **JSON + HTML report** with pass/fail status, render times, and direct links
9. Prints a **console summary** listing every failed page with its Power BI service URL

If any visual fails to render, the pipeline fails and the team is alerted.

---

## Architecture

```
                    GitHub Actions (CI/CD)
                            |
                            v
              +-----------------------------+
              |   Service Principal Auth    |
              |   (Azure AD OAuth2)         |
              +------------+----------------+
                           | Access Token
                           v
              +-----------------------------+
              |   Power BI REST API         |
              |   +- List workspace reports |
              |   +- Fetch dataset metadata |
              |   +- Detect RLS flags       |
              |   +- Generate embed tokens  |
              +------------+----------------+
                           | Embed Tokens
                           v
              +-----------------------------+
              |   Playwright + Chromium     |
              |   +- Load Power BI JS SDK   |
              |   +- Embed each report      |
              |   +- Navigate all pages     |
              |   +- Monitor render events  |
              |   +- Screenshot failures    |
              +------------+----------------+
                           |
                           v
              +-----------------------------+
              |   Test Artifacts            |
              |   +- HTML report            |
              |   +- JSON results + metrics |
              |   +- Failure screenshots    |
              |   +- Console summary + URLs |
              +-----------------------------+
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Test Framework** | Pytest with pytest-playwright, pytest-xdist (parallel) |
| **Browser Automation** | Playwright (headless Chromium) |
| **Power BI Integration** | Power BI JavaScript SDK + REST API |
| **Authentication** | Azure AD Service Principal (OAuth2 client_credentials) |
| **CI/CD** | GitHub Actions |
| **Reporting** | GitHub Pages (auto-deployed HTML report) |
| **Language** | Python 3.11+ |

---

## What Gets Tested

Every function in the pipeline has its own test. The framework validates each layer independently before running the full visual scan:

| Test | What It Validates |
|------|-------------------|
| `test_required_env_vars_exist` | Service Principal credentials are set (`SP_CLIENT_ID`, `SP_CLIENT_SECRET`, `SP_TENANT_ID`) |
| `test_environment_default` | `ENVIRONMENT` is a valid value (`prod`, `dev`, `test`, `qa`) |
| `test_reports_loaded` | At least one report was loaded from workspace metadata |
| `test_report_structure` | Every report has the required fields (`Id`, `Name`, `EmbedUrl`, `WorkspaceId`) |
| `test_report_ids_unique` | No duplicate report IDs in the metadata |
| `test_access_token_success` | OAuth2 token acquisition against Azure AD works and returns a valid token |
| `test_embed_token_success` | Embed token generation via the Power BI REST API works for at least one report |
| `test_pbi_rendering_validation` | **Full visual scan**, embeds each report in headless Chromium, navigates every page, monitors render events, detects errors, captures screenshots of failures |

The first 7 tests act as **pre-flight checks**, if authentication or metadata is broken, you get a clear failure before the pipeline spends time on visual rendering.

---

## Auto-Refreshing Metadata

Report metadata is **automatically refreshed** at the start of every test session. The `pytest_sessionstart` hook in `conftest.py` runs `get_workspace_reports_datasets.py` before any tests execute. This ensures:

- New reports added to the workspace are picked up immediately
- Removed reports are no longer tested
- RLS flag changes on datasets are reflected
- No stale metadata issues, every run is up to date

If the metadata refresh fails (e.g., authentication error, network issue), the entire test session is aborted with a clear error message.

You do not need to run the metadata script manually before running tests locally, it happens automatically.

---

## Row-Level Security (RLS) Handling

A key feature of this framework is **automatic RLS detection and handling**. Many Power BI datasets enforce Row-Level Security, which requires an effective identity (username + role) when generating embed tokens.

### How It Works

1. **Auto-detection**, The metadata script queries each dataset via the Power BI REST API and reads the `isEffectiveIdentityRequired` and `isEffectiveIdentityRolesRequired` flags. These are stored in the metadata JSON so the test runner knows which datasets need an identity.

2. **Automatic token generation**, When a dataset requires RLS, the embed token request automatically includes an effective identity with the username `TestUser` and the role from `DEFAULT_RLS_ROLE`.

3. **Per-report override**, You can set a `"Role"` field on any report in the metadata JSON to use a specific role instead of the default.

### Important: Setting Up a Global RLS User

If your workspace contains reports with RLS, you must define a **global RLS role that has access to all data** as the default. This is because the automated tests need to see the full report, not a filtered view.

In your `.env` file (or GitHub Secrets):

```
DEFAULT_RLS_ROLE = 'Master'
```

This role must exist in the dataset's RLS configuration in Power BI Desktop / Service, and it should have **no filters applied** (or filters that return all rows). The embed token will use this role with the username `TestUser`.

If you don't set `DEFAULT_RLS_ROLE` and your datasets require RLS, the embed token generation will fail for those reports.

| Scenario | Behavior |
|----------|----------|
| Dataset has no RLS | No effective identity sent, works out of the box |
| Dataset has RLS | Effective identity sent with username `TestUser` and `DEFAULT_RLS_ROLE` |
| Per-report override | Set `"Role"` field in `reports_datasets.json` to override the default |

## Failed Page Screenshots

When a visual rendering error is detected on a page, the framework automatically:

1. **Navigates back** to the failed page in the embedded report
2. **Captures a full screenshot** of the Power BI container showing the broken state
3. **Saves the screenshot** to `tests/test-results/{page_name}_{worker_id}.png`
4. **Embeds screenshots** as base64 in the HTML report (self-contained, no external files)
5. **Uploads all screenshots** as GitHub Actions artifacts for review

Screenshots are only taken for failed pages to keep artifacts small.

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/visual-tests.yml`) runs on:
- Every **push** to `main` (for testing purposes)
- Every **pull request** to `main` (for testing purposes)
- **Manual trigger** (workflow_dispatch)

### Pipeline Steps

```
Checkout -> Python 3.11 -> Install Deps -> Install Chromium
    -> Fetch Report Metadata -> Run Visual Tests
    -> Upload Artifacts -> Deploy to GitHub Pages
```

Test artifacts (HTML report, JSON results, screenshots) are:
- Uploaded as GitHub Actions artifacts
- Deployed to GitHub Pages at `/report/report.html`

### Required GitHub Secrets & Variables

| Name | Type | Description |
|------|------|-------------|
| `SP_CLIENT_ID` | Secret | Service Principal Application (client) ID |
| `SP_TENANT_ID` | Secret | Azure AD Tenant ID |
| `SP_CLIENT_SECRET` | Secret | Service Principal client secret |
| `ENVIRONMENT` | Secret | `prod` or `gov` (for GCC High / sovereign clouds) |
| `DEFAULT_RLS_ROLE` | Secret | Default RLS role for datasets with Row-Level Security (e.g., `Master`) |
| `WORKSPACE_ID` | Variable | Power BI Workspace ID |

---

## Setup & Local Development

### Prerequisites

- Python 3.11+
- A Power BI workspace with published reports
- An Azure AD Service Principal with **Contributor** access to the workspace ([setup guide](https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal))
- If your workspace has RLS-enabled datasets: an RLS role with full data access

### Install

```bash
git clone https://github.com/FilippDor/Fabric-UI-testing.git
cd Fabric-UI-testing

python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

pip install -r requirements_visual_test.txt
playwright install 

cp .env.example .env
# Edit .env with your credentials
```

### Environment Variables

```bash
SP_CLIENT_ID = 'your-service-principal-client-id'
SP_TENANT_ID = 'your-azure-tenant-id'
SP_CLIENT_SECRET = 'your-service-principal-client-secret'
WORKSPACE_ID = 'your-power-bi-workspace-id'
ENVIRONMENT = 'prod'                  # 'prod' or 'gov'
DEFAULT_RLS_ROLE = 'Master'           # RLS role with full data access
```

### Run

```bash
# Run all tests (metadata is refreshed automatically)
pytest

# Run tests in parallel
pytest -n auto

# Run only the visual scan (skip unit tests)
pytest -k "test_pbi_rendering_validation"

# Run only unit/pre-flight tests
pytest -k "not test_pbi_rendering_validation"
```

### Output

| Artifact | Location |
|----------|----------|
| Custom HTML report | `tests/test-results/report.html` |
| Playwright HTML report | `tests/test-results/playwright_report.html` |
| JSON results | `tests/test-results/all_reports_results.json` |
| Failure screenshots | `tests/test-results/*.png` |

---

## Project Structure

```
+-- .github/workflows/
|   +-- visual-tests.yml                    # CI/CD pipeline
+-- conftest.py                             # Pytest hooks: auto-refresh metadata,
|                                           #   result aggregation, console summary,
|                                           #   HTML report generation
+-- pytest.ini                              # Pytest configuration
+-- requirements_visual_test.txt            # Python dependencies
+-- .env.example                            # Environment variable template
+-- helper_functions/
|   +-- token_helpers.py                    # Service Principal auth, embed tokens,
|   |                                       #   RLS identity handling, API endpoints
|   +-- get_workspace_reports_datasets.py   # Workspace discovery: reports, datasets,
|   |                                       #   RLS flag detection
|   +-- file_reader.py                      # JSON file loading utility
|   +-- log_utils.py                        # Console logging helper
+-- metadata/reports/
|   +-- reports_datasets.json               # Auto-generated report + dataset metadata
+-- tests/
    +-- test_visual_render_embed_multiple_pics.py
    |   # - Unit tests: env vars, report structure, auth, embed tokens
    |   # - Visual scan: embed reports, navigate pages, detect errors,
    |   #   capture screenshots, save results
    +-- test-results/                       # Generated artifacts (gitignored)
```

### Key Files

| File | Purpose |
|------|---------|
| `conftest.py` | `pytest_sessionstart`: auto-refreshes workspace metadata before tests. `pytest_sessionfinish`: aggregates results from parallel workers, prints console summary with failed page URLs, generates HTML report with embedded screenshots. |
| `token_helpers.py` | `get_access_token()`: OAuth2 client_credentials flow. `get_report_embed_token()`: generates embed tokens with RLS identity when required. `create_report_embed_info()`: maps metadata to typed objects. `get_api_endpoints()`: returns prod/gov API URLs. |
| `get_workspace_reports_datasets.py` | Fetches all reports and datasets from the workspace, detects RLS flags (`isEffectiveIdentityRequired`, `isEffectiveIdentityRolesRequired`), writes metadata JSON. |
| `file_reader.py` | `read_json_files_from_folder()`: reads all JSON files from a folder and flattens the `reports` arrays. |

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `playwright` | 1.58.0 | Browser automation (headless Chromium) |
| `pytest` | 9.0.2 | Test framework |
| `pytest-html` | 4.2.0 | HTML report generation |
| `pytest-playwright` | 0.7.2 | Pytest + Playwright integration |
| `pytest-xdist` | 3.8.0 | Parallel test execution across workers |
| `python-dotenv` | 1.2.1 | Environment variable loading from `.env` |
| `requests` | 2.32.5 | HTTP client for Power BI REST API |