import os
import json
import time
from pathlib import Path
import pytest
from playwright.sync_api import Page
from dotenv import load_dotenv
load_dotenv()

from helper_functions.token_helpers import (
    get_access_token,
    get_report_embed_token,
    create_report_embed_info,
    get_api_endpoints,
    TestSettings,
)
from helper_functions.file_reader import read_json_files_from_folder
from helper_functions.log_utils import log_to_console

# -------------------- ENV --------------------
CLIENT_ID = os.environ.get("SP_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SP_CLIENT_SECRET")
TENANT_ID = os.environ.get("SP_TENANT_ID")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")

if not CLIENT_ID or not CLIENT_SECRET or not TENANT_ID:
    raise RuntimeError("Missing required environment variables.")

# -------------------- PATHS --------------------
BASE_DIR = Path(__file__).resolve().parent.parent
TEST_RESULTS_DIR = BASE_DIR / "tests" / "test-results"
TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)  # Playwright ensures clean, but just in case

REPORTS_PATH = BASE_DIR / "metadata" / "reports"
reports = read_json_files_from_folder(REPORTS_PATH)

if not reports:
    raise RuntimeError(f"No reports found in {REPORTS_PATH}")

endpoints = get_api_endpoints(ENVIRONMENT)

# -------------------- FIXTURES --------------------
@pytest.fixture(scope="session")
def access_token() -> str:
    settings = TestSettings(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        tenant_id=TENANT_ID,
        environment=ENVIRONMENT,
    )
    return get_access_token(settings)

@pytest.fixture(scope="session")
def browser_context_args():
    return {"viewport": {"width": 1280, "height": 800}}

# -------------------- TESTS --------------------
@pytest.mark.parametrize("report", reports, ids=lambda r: f"{r['Name']} ({r['Id']})")
def test_pbi_rendering_validation(page: Page, access_token: str, report: dict):
    start_time = time.time()

    page.goto("about:blank")
    page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/powerbi-client/2.23.1/powerbi.min.js")

    embed_info = create_report_embed_info(report)
    embed_token = get_report_embed_token(embed_info, endpoints, access_token)

    report_info = {
        "reportId": embed_info.report_id,
        "embedUrl": report["EmbedUrl"],
        "embedToken": embed_token,
        "workspaceId": report["WorkspaceId"],
    }

    # -------------------- SCAN PAGES --------------------
    scan_results = page.evaluate(
        """
        async (reportInfo) => {
            const t0 = performance.now();
            const pbi = window['powerbi-client'];
            const models = pbi.models;

            const container = document.createElement('div');
            container.id = 'powerbi-container';
            container.style.width = '1200px';
            container.style.height = '800px';
            document.body.appendChild(container);

            const powerbi = new pbi.service.Service(
                pbi.factories.hpmFactory,
                pbi.factories.wpmpFactory,
                pbi.factories.routerFactory
            );

            const report = powerbi.embed(container, {
                type: 'report',
                id: reportInfo.reportId,
                embedUrl: reportInfo.embedUrl,
                accessToken: reportInfo.embedToken,
                tokenType: models.TokenType.Embed,
                permissions: models.Permissions.Read,
                viewMode: models.ViewMode.View,
                settings: { visualRenderedEvents: true }
            });

            const reportLoadTime = await new Promise(res =>
                report.on('loaded', () => res(performance.now()))
            );

            const pages = await report.getPages();
            const allPages = {};
            const failedPages = [];

            for (const pageObj of pages) {
                const pageStart = performance.now();
                const pageName = pageObj.name;

                let errorDetected = false;
                const visuals = await pageObj.getVisuals();
                let renderedVisuals = 0;
                const pageErrors = {};

                const onError = (event) => {
                    const visualId = event?.detail?.visualName || event?.detail?.visualId || 'unknown';
                    pageErrors[visualId] = event?.detail?.message || 'Unknown Power BI error';
                    errorDetected = true;
                };
                const onRendered = () => renderedVisuals++;

                report.on('error', onError);
                report.on('visualRendered', onRendered);

                await pageObj.setActive();

                await Promise.race([
                    new Promise(resolve => {
                        const check = () => {
                            if (errorDetected || renderedVisuals >= visuals.length) resolve();
                            else setTimeout(check, 1000);
                        };
                        check();
                    }),
                    new Promise(resolve => setTimeout(resolve, 15000))
                ]);

                report.off('error', onError);
                report.off('visualRendered', onRendered);

                const pageEnd = performance.now();
                const duration = pageEnd - pageStart;

                allPages[pageName] = {
                    errors: pageErrors,
                    duration,
                    embedUrl: `https://app.powerbi.com/reportEmbed?reportId=${reportInfo.reportId}&pageName=${pageName}`,
                    serviceUrl: `https://app.powerbi.com/groups/${reportInfo.workspaceId}/reports/${reportInfo.reportId}/${pageName}`
                };

                if (Object.keys(pageErrors).length > 0) {
                    failedPages.push(pageName);
                }
            }

            return {
                allPages,
                failedPages,
                reportLoadTime,
                totalDuration: performance.now() - t0
            };
        }
        """,
        report_info,
    )

    # -------------------- SCREENSHOTS (only failing pages) --------------------
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")

    for page_name in scan_results["failedPages"]:
        page.evaluate(
            """
            async (pageName) => {
                const report = window.powerbi.get(document.querySelector('#powerbi-container'));
                const pages = await report.getPages();
                const target = pages.find(p => p.name === pageName);
                if (target) await target.setActive();
            }
            """,
            page_name
        )
        screenshot_path = TEST_RESULTS_DIR / f"{page_name}_{worker_id}.png"
        page.locator("#powerbi-container").screenshot(path=str(screenshot_path))
        log_to_console(f"[INFO] Screenshot saved: {screenshot_path}", False)

    # -------------------- SAVE RESULTS (all pages) --------------------
    end_time = time.time()

    # Ensure directory exists (important for xdist)
    TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    worker_file = TEST_RESULTS_DIR / f"results_{worker_id}.json"

    existing_results = (
        json.loads(worker_file.read_text(encoding="utf-8"))
        if worker_file.exists()
        else []
    )

    #Build result FIRST
    result_data = {
        "reportId": report["Id"],
        "reportName": report["Name"],
        "environment": ENVIRONMENT,
        "pages": scan_results["allPages"],       # all pages (pass + fail)
        "failedPages": scan_results["failedPages"],  # screenshot targets
        "reportLoadTime": scan_results["reportLoadTime"],
        "totalDuration": scan_results["totalDuration"],
        "pythonDuration": end_time - start_time,
    }

    #Append ONCE
    existing_results.append(result_data)

    #Write ONCE
    worker_file.write_text(
        json.dumps(existing_results, indent=2),
        encoding="utf-8"
    )

    log_to_console(
        f"[INFO] Appended results for report {report['Name']} -> {worker_file}",
        False,
    )

    # -------------------- LOG PASSED / FAILED --------------------
    passed_pages = [name for name, info in scan_results["allPages"].items() if not info["errors"]]
    failed_pages = [name for name, info in scan_results["allPages"].items() if info["errors"]]

    if passed_pages:
        print("\n[PASS] Pages rendered successfully:")
        for p in passed_pages:
            print(f"  ✓ {p}")

    if failed_pages:
        print("\n[FAIL] Pages with visual errors:")
        for page_name in failed_pages:
            info = scan_results["allPages"][page_name]
            print(f"  ✗ {page_name} -> {info['serviceUrl']}")

    # -------------------- ASSERTIONS --------------------
    assert len(failed_pages) == 0, f"{len(failed_pages)} pages failed visuals."

    # ==================== UNIT TESTS ====================
def test_required_env_vars_exist():
    assert CLIENT_ID, "SP_CLIENT_ID is missing"
    assert CLIENT_SECRET, "SP_CLIENT_SECRET is missing"
    assert TENANT_ID, "SP_TENANT_ID is missing"


def test_environment_default():
    assert ENVIRONMENT in {"prod", "dev", "test", "qa"}


def test_reports_loaded():
    assert len(reports) > 0


def test_report_structure():
    required_fields = {"Id", "Name", "EmbedUrl", "WorkspaceId"}
    for report in reports:
        assert required_fields.issubset(report.keys())


def test_report_ids_unique():
    ids = [r["Id"] for r in reports]
    assert len(ids) == len(set(ids))


def test_access_token_success():
    settings = TestSettings(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        tenant_id=TENANT_ID,
        environment=ENVIRONMENT,
    )

    token = get_access_token(settings)
    assert isinstance(token, str)
    assert len(token) > 20


def test_embed_token_success():
    report = reports[0]
    embed_info = create_report_embed_info(report)

    settings = TestSettings(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        tenant_id=TENANT_ID,
        environment=ENVIRONMENT,
    )

    access_token = get_access_token(settings)
    token = get_report_embed_token(embed_info, endpoints, access_token)

    assert isinstance(token, str)
    assert len(token) > 20