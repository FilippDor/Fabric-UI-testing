import json
import os
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Page

load_dotenv()

from helper_functions.file_reader import read_json_files_from_folder
from helper_functions.log_utils import log_to_console
from helper_functions.token_helpers import (
    TestSettings,
    create_report_embed_info,
    get_access_token,
    get_api_endpoints,
    get_report_embed_token,
)

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
TEST_RESULTS_DIR.mkdir(
    parents=True, exist_ok=True
)  # Playwright ensures clean, but just in case

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
@pytest.mark.integration
@pytest.mark.parametrize("report", reports, ids=lambda r: f"{r['Name']} ({r['Id']})")
def test_pbi_rendering_validation(page: Page, access_token: str, report: dict):
    start_time = time.time()

    page.goto("about:blank")
    page.add_script_tag(
        url="https://cdnjs.cloudflare.com/ajax/libs/powerbi-client/2.23.1/powerbi.min.js"
    )

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

                const result = {
                    success: false,
                    allPages: {},
                    failedPages: [],
                    reportLoadTime: 0,
                    totalDuration: 0,
                    fatalError: null,
                    stack: null
                };

                try {

                    const t0 = performance.now();

                    const pbi = window['powerbi-client'];
                    if (!pbi) throw new Error("Power BI client not loaded");

                    const models = pbi.models;

                    // --- CREATE CONTAINER ---
                    let container = document.getElementById('powerbi-container');
                    if (!container) {
                        container = document.createElement('div');
                        container.id = 'powerbi-container';
                        container.style.width = '1200px';
                        container.style.height = '800px';
                        document.body.appendChild(container);
                    }

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

                    // --- WAIT FOR REPORT LOAD ---
                    result.reportLoadTime = await new Promise((resolve, reject) => {
                        const timeout = setTimeout(() => reject(new Error("Report load timeout")), 30000);
                        report.on('loaded', () => {
                            clearTimeout(timeout);
                            resolve(performance.now());
                        });
                    });

                    const allPages = result.allPages;
                    const failedPages = result.failedPages;

                    // -------------------- PAGE SCAN --------------------
                    const pages = await report.getPages();

                    for (const pageObj of pages) {

                        const pageStart = performance.now();
                        const pageName = pageObj.name;
                        const pageErrors = {};

                        const onError = (event) => {
                            const id = event?.detail?.visualName || event?.detail?.visualId || "unknown";
                            const msg = event?.detail?.message || "Unknown Power BI error";
                            pageErrors[id] = msg;
                        };

                        report.on("error", onError);

                        await pageObj.setActive();

                        const visuals = await pageObj.getVisuals();

                        await new Promise(resolve => {
                            let lastRender = Date.now();

                            const onRendered = () => lastRender = Date.now();
                            report.on("visualRendered", onRendered);

                            const check = () => {
                                const now = Date.now();
                                if (now - lastRender > 2000) {
                                    report.off("visualRendered", onRendered);
                                    resolve();
                                    return;
                                }
                                setTimeout(check, 500);
                            };

                            check();
                        });

                        report.off("error", onError);

                        const duration = performance.now() - pageStart;

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

                    // -------------------- BOOKMARK SCAN --------------------

                    const flattenBookmarks = (bookmarks) => {
                        const flat = [];
                        for (const bm of bookmarks) {
                            if (bm.children?.length) {
                                flat.push(...flattenBookmarks(bm.children));
                            } else if (bm.state) {
                                flat.push(bm);
                            }
                        }
                        return flat;
                    };

                    let allBookmarks = [];
                    try {
                        const rawBookmarks = await report.bookmarksManager.getBookmarks();
                        allBookmarks = flattenBookmarks(rawBookmarks);
                    } catch (_) {
                        // bookmarks not available
                    }

                    for (const bookmark of allBookmarks) {

                        const bmStart = performance.now();
                        const bmKey = "bookmark:" + bookmark.name;
                        const bmErrors = {};

                        const onError = (event) => {
                            const id = event?.detail?.visualName || event?.detail?.visualId || "unknown";
                            const msg = event?.detail?.message || "Unknown Power BI error";
                            bmErrors[id] = msg;
                        };

                        report.on("error", onError);

                        try {

                            // Apply bookmark safely (no rejection)
                            await report.bookmarksManager.applyState(bookmark.state);

                            // Wait for visuals to settle (idle 2s OR 15s hard cap)
                            await new Promise(resolve => {

                                let lastRender = Date.now();
                                const start = Date.now();

                                const onRendered = () => lastRender = Date.now();
                                report.on("visualRendered", onRendered);

                                const check = () => {
                                    const now = Date.now();

                                    if (now - lastRender > 2000) {
                                        report.off("visualRendered", onRendered);
                                        resolve();
                                        return;
                                    }

                                    if (now - start > 15000) {
                                        report.off("visualRendered", onRendered);
                                        resolve();
                                        return;
                                    }

                                    setTimeout(check, 500);
                                };

                                check();
                            });

                            const duration = performance.now() - bmStart;

                            allPages[bmKey] = {
                                errors: bmErrors,
                                duration,
                                bookmarkDisplayName: bookmark.displayName || bookmark.name,
                                embedUrl: `https://app.powerbi.com/reportEmbed?reportId=${reportInfo.reportId}&bookmarkGuid=${bookmark.name}`,
                                serviceUrl: `https://app.powerbi.com/groups/${reportInfo.workspaceId}/reports/${reportInfo.reportId}?bookmarkGuid=${bookmark.name}`
                            };

                            if (Object.keys(bmErrors).length > 0) {
                                failedPages.push(bmKey);
                            }

                        } catch (err) {

                            allPages[bmKey] = {
                                errors: { general: err?.message || "Bookmark failed" },
                                duration: performance.now() - bmStart,
                                bookmarkDisplayName: bookmark.displayName || bookmark.name
                            };

                            failedPages.push(bmKey);
                        }

                        report.off("error", onError);
                    }

                    result.success = true;
                    result.totalDuration = performance.now() - t0;
                    return result;

                } catch (err) {

                    result.success = false;
                    result.fatalError = err?.message || String(err);
                    result.stack = err?.stack || null;
                    return result;
                }
            }
            """,
        report_info,
    )

    # -------------------- SCREENSHOTS (only failing pages/bookmarks) --------------------
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")

    for entry_key in scan_results["failedPages"]:
        if entry_key.startswith("bookmark:"):
            bookmark_name = entry_key[len("bookmark:") :]
            page.evaluate(
                """
                async (bookmarkName) => {
                    const report = window.powerbi.get(document.querySelector('#powerbi-container'));
                    await report.bookmarksManager.apply(bookmarkName);
                }
                """,
                bookmark_name,
            )
            page.wait_for_timeout(800)
            screenshot_path = (
                TEST_RESULTS_DIR / f"bookmark_{bookmark_name}_{worker_id}.png"
            )
        else:
            page.evaluate(
                """
                async (pageName) => {
                    const report = window.powerbi.get(document.querySelector('#powerbi-container'));
                    const pages = await report.getPages();
                    const target = pages.find(p => p.name === pageName);
                    if (target) await target.setActive();
                }
                """,
                entry_key,
            )
            page.wait_for_timeout(800)
            screenshot_path = TEST_RESULTS_DIR / f"{entry_key}_{worker_id}.png"

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

    # Build result FIRST
    result_data = {
        "reportId": report["Id"],
        "reportName": report["Name"],
        "environment": ENVIRONMENT,
        "pages": scan_results["allPages"],  # all pages (pass + fail)
        "failedPages": scan_results["failedPages"],  # screenshot targets
        "reportLoadTime": scan_results["reportLoadTime"],
        "totalDuration": scan_results["totalDuration"],
        "pythonDuration": end_time - start_time,
    }

    # Append ONCE
    existing_results.append(result_data)

    # Write ONCE
    worker_file.write_text(json.dumps(existing_results, indent=2), encoding="utf-8")

    log_to_console(
        f"[INFO] Appended results for report {report['Name']} -> {worker_file}",
        False,
    )

    # -------------------- LOG PASSED / FAILED --------------------
    passed_pages = [
        name
        for name, info in scan_results["allPages"].items()
        if not info["errors"] and "bookmarkDisplayName" not in info
    ]
    failed_pages = [
        name
        for name, info in scan_results["allPages"].items()
        if info["errors"] and "bookmarkDisplayName" not in info
    ]
    passed_bookmarks = [
        name
        for name, info in scan_results["allPages"].items()
        if not info["errors"] and "bookmarkDisplayName" in info
    ]
    failed_bookmarks = [
        name
        for name, info in scan_results["allPages"].items()
        if info["errors"] and "bookmarkDisplayName" in info
    ]

    if passed_pages:
        print("\n[PASS] Pages rendered successfully:")
        for p in passed_pages:
            print(f"  ✓ {p}")

    if passed_bookmarks:
        print("\n[PASS] Bookmarks rendered successfully:")
        for b in passed_bookmarks:
            display = scan_results["allPages"][b].get("bookmarkDisplayName", b)
            print(f"  ✓ {display}")

    if failed_pages:
        print("\n[FAIL] Pages with visual errors:")
        for page_name in failed_pages:
            info = scan_results["allPages"][page_name]
            print(f"  ✗ {page_name} -> {info['serviceUrl']}")

    if failed_bookmarks:
        print("\n[FAIL] Bookmarks with visual errors:")
        for bm_key in failed_bookmarks:
            info = scan_results["allPages"][bm_key]
            display = info.get("bookmarkDisplayName", bm_key)
            print(f"  ✗ {display} -> {info['serviceUrl']}")

    # -------------------- ASSERTIONS --------------------
    total_failures = len(failed_pages) + len(failed_bookmarks)
    assert (
        total_failures == 0
    ), f"{len(failed_pages)} pages and {len(failed_bookmarks)} bookmarks failed visuals."
