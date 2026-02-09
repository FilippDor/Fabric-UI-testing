import os
import time
import json
from pathlib import Path
from helper_functions.log_utils import log_to_console

BASE_DIR = Path(__file__).resolve().parent
TEST_RESULTS_DIR = BASE_DIR / "tests" / "test-results"


def pytest_sessionfinish(session, exitstatus):
    # Only run once (not per xdist worker)
    if hasattr(session.config, "workerinput"):
        return

    all_results = []

    # Collect per-worker JSONs
    for worker_file in TEST_RESULTS_DIR.glob("results_*.json"):
        try:
            worker_reports = json.loads(worker_file.read_text(encoding="utf-8"))
            all_results.extend(worker_reports)
        except Exception as e:
            log_to_console(f"[WARN] Failed reading {worker_file}: {e}", True)

    # ---------------- SUMMARY ----------------
    total_pages = 0
    failed_pages = 0

    for report in all_results:
        pages = report.get("pages", {})
        total_pages += len(pages)
        failed_pages += sum(1 for p in pages.values() if p.get("errors"))

    summary = {
        "totalReports": len(all_results),
        "totalPages": total_pages,
        "failedPages": failed_pages,
        "passedPages": total_pages - failed_pages,
        "passRate": round(
            ((total_pages - failed_pages) / total_pages) * 100, 2
        ) if total_pages else 0,
    }

    final_output = {
        "environment": os.environ.get("ENVIRONMENT", "prod"),
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        "reports": all_results,
    }

    final_json = TEST_RESULTS_DIR / "all_reports_results.json"
    final_json.parent.mkdir(parents=True, exist_ok=True)
    final_json.write_text(json.dumps(final_output, indent=2), encoding="utf-8")

    log_to_console(f"[INFO] Final aggregated JSON: {final_json}", True)

    # Optional: clean worker JSONs
    for f in TEST_RESULTS_DIR.glob("results_*.json"):
        f.unlink()
