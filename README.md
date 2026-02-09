# Power BI Visual Regression Testing

Automated visual regression testing for Power BI reports using **Pytest**, **Playwright**, and the **Power BI JavaScript SDK**. The pipeline authenticates via a Service Principal, embeds each report in a headless browser, iterates through every page, and detects visual rendering errors automatically.

## How It Works

```
Service Principal credentials
        │
        ▼
Azure AD OAuth2 → Access Token
        │
        ▼
Power BI REST API → Embed Token (per report)
        │
        ▼
Playwright (headless Chromium)
  ├─ Loads Power BI JS SDK
  ├─ Embeds report in DOM
  ├─ Iterates through all pages
  ├─ Monitors visual rendering events
  ├─ Captures errors + screenshots on failure
  └─ Records render times
        │
        ▼
Test Results (JSON + HTML + screenshots)
```

## Prerequisites

- Python 3.11+
- A Power BI workspace with reports
- An Azure AD **Service Principal** with access to the workspace ([setup guide](https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal))
- Playwright browsers installed

## Setup

```bash
# Clone the repo
git clone https://github.com/FilippDor/Fabric_CICD.git
cd Fabric_CICD

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements_visual_test.txt

# Install Playwright browsers
playwright install --with-deps chromium

# Configure environment variables
cp .env.example .env
# Edit .env with your Service Principal credentials and workspace ID
```

## Running Tests

### Fetch report metadata from workspace

```bash
python -m helper_functions.get_workspace_reports_datasets
```

This queries the Power BI REST API and saves report metadata to `metadata/reports/reports_datasets.json`.

### Run visual tests

```bash
# Standard run
pytest

# Parallel execution (uses all CPU cores)
pytest -n auto
```

### Test output

| Artifact | Location |
|----------|----------|
| HTML report | `tests/test-results/playwright_report.html` |
| Aggregated JSON results | `tests/test-results/all_reports_results.json` |
| Failure screenshots | `tests/test-results/*.png` |

## CI/CD (GitHub Actions)

The pipeline runs on every push/PR to `main` and can be triggered manually.

**Required GitHub Secrets:**

| Secret | Description |
|--------|-------------|
| `SP_CLIENT_ID` | Service Principal Application (client) ID |
| `SP_TENANT_ID` | Azure AD Tenant ID |
| `SP_CLIENT_SECRET` | Service Principal client secret |
| `WORKSPACE_ID` | Power BI Workspace ID |
| `ENVIRONMENT` | `prod` or `gov` |

Test artifacts (HTML report, JSON results, screenshots) are uploaded as GitHub Actions artifacts after each run.

## Project Structure

```
├── conftest.py                  # Pytest hooks - aggregates worker results
├── pytest.ini                   # Pytest configuration
├── requirements_visual_test.txt # Python dependencies
├── helper_functions/
│   ├── token_helpers.py         # Service Principal auth & embed token generation
│   ├── file_reader.py           # JSON file utilities
│   ├── log_utils.py             # Logging
│   └── get_workspace_reports_datasets.py  # Fetch reports from workspace
├── metadata/
│   └── reports/
│       └── reports_datasets.json  # Report metadata (auto-generated)
└── tests/
    └── test_visual_render_embed_multiple_pics.py  # Visual regression tests
```

## What Gets Tested

For each report in the workspace:
1. **Configuration checks** - env vars, report metadata validity, unique IDs
2. **Authentication** - Service Principal token acquisition
3. **Embed token generation** - per-report embed tokens
4. **Visual rendering** - every page of every report is rendered and validated
5. **Error detection** - Power BI SDK visual errors are captured
6. **Performance** - render time per page is recorded
