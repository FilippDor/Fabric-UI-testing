import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from helper_functions.report_html import generate_html_report

BASE_DIR = Path(__file__).resolve().parent
TEST_RESULTS_DIR = BASE_DIR / "tests" / "test-results"


def pytest_sessionstart(session):
    """Refresh report metadata before tests (main process only)."""
    if hasattr(session.config, "workerinput"):
        return

    script = BASE_DIR / "helper_functions" / "get_workspace_reports_datasets.py"
    print(f"[INFO] Running {script.name} to refresh report metadata...")

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"[ERROR] {script.name} failed (exit {result.returncode})")
        if result.stderr:
            print(result.stderr.strip())
        raise SystemExit(f"{script.name} failed — aborting test session")


def pytest_sessionfinish(session, exitstatus):
    """Aggregate results, print summary, generate HTML report (main process only)."""
    if hasattr(session.config, "workerinput"):
        return

    all_results = []
    for worker_file in TEST_RESULTS_DIR.glob("results_*.json"):
        try:
            all_results.extend(json.loads(worker_file.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[WARN] Failed reading {worker_file}: {e}")

    total_pages = 0
    failed_pages = 0
    total_bookmarks = 0
    failed_bookmarks = 0
    for report in all_results:
        pages = report.get("pages", {})
        for entry_info in pages.values():
            if "bookmarkDisplayName" in entry_info:
                total_bookmarks += 1
                if entry_info.get("errors"):
                    failed_bookmarks += 1
            else:
                total_pages += 1
                if entry_info.get("errors"):
                    failed_pages += 1

    summary = {
        "totalReports": len(all_results),
        "totalPages": total_pages,
        "failedPages": failed_pages,
        "passedPages": total_pages - failed_pages,
        "passRate": (
            round(((total_pages - failed_pages) / total_pages) * 100, 2) if total_pages else 0
        ),
        "totalBookmarks": total_bookmarks,
        "failedBookmarks": failed_bookmarks,
    }

    final_output = {
        "environment": os.environ.get("ENVIRONMENT", "prod"),
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        "reports": all_results,
    }

    # JSON report
    final_json = TEST_RESULTS_DIR / "all_reports_results.json"
    final_json.parent.mkdir(parents=True, exist_ok=True)
    final_json.write_text(json.dumps(final_output, indent=2), encoding="utf-8")
    print(f"[INFO] Final aggregated JSON: {final_json}")

    # HTML report
    html_report = TEST_RESULTS_DIR / "report.html"
    html_report.write_text(generate_html_report(final_output, TEST_RESULTS_DIR), encoding="utf-8")
    print(f"[INFO] HTML report: {html_report}")

    if not os.environ.get("CI"):
        webbrowser.open(html_report.as_uri())

    # Clean worker JSONs
    for f in TEST_RESULTS_DIR.glob("results_*.json"):
        f.unlink()
