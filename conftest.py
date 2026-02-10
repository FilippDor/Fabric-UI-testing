import os
import sys
import time
import json
import base64
import subprocess
import webbrowser
from pathlib import Path
from helper_functions.log_utils import log_to_console

BASE_DIR = Path(__file__).resolve().parent
TEST_RESULTS_DIR = BASE_DIR / "tests" / "test-results"


def pytest_sessionstart(session):
    """Run get_workspace_reports_datasets.py before tests to ensure metadata is up to date."""
    # Only run on the main process, not on xdist workers
    if hasattr(session.config, "workerinput"):
        return

    script = BASE_DIR / "helper_functions" / "get_workspace_reports_datasets.py"
    log_to_console(f"[INFO] Running {script.name} to refresh report metadata...", True)

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
    )

    if result.stdout:
        log_to_console(result.stdout.strip(), True)
    if result.returncode != 0:
        log_to_console(f"[ERROR] {script.name} failed (exit {result.returncode})", True)
        if result.stderr:
            log_to_console(result.stderr.strip(), True)
        raise SystemExit(f"{script.name} failed aborting test session")


def _generate_html_report(final_output):
    """Generate a standalone HTML report with failed pages and embedded screenshots."""
    reports = final_output.get("reports", [])
    summary = final_output.get("summary", {})
    generated_at = final_output.get("generatedAt", "")
    environment = final_output.get("environment", "")

    failed_sections = []
    for report in reports:
        report_name = report.get("reportName", "Unknown")
        report_id = report.get("reportId", "")
        pages = report.get("pages", {})

        for page_name, page_info in pages.items():
            errors = page_info.get("errors", {})
            if not errors:
                continue

            service_url = page_info.get("serviceUrl", "")
            duration = page_info.get("duration", 0)

            # Find matching screenshot
            screenshot_html = ""
            for png in TEST_RESULTS_DIR.glob(f"{page_name}_*.png"):
                img_data = base64.b64encode(png.read_bytes()).decode("utf-8")
                screenshot_html = f'<img src="data:image/png;base64,{img_data}" alt="{page_name}" style="max-width:100%;border:1px solid #ddd;border-radius:4px;margin-top:8px;" />'
                break

            error_rows = "".join(
                f"<tr><td>{vid}</td><td>{msg}</td></tr>" for vid, msg in errors.items()
            )

            failed_sections.append(
                f"""
            <div class="card failed">
                <h3>{report_name} &mdash; {page_name}</h3>
                <p class="meta">Report ID: {report_id} | Duration: {duration:.0f}ms</p>
                <p><a href="{service_url}" target="_blank">{service_url}</a></p>
                <table>
                    <thead><tr><th>Visual</th><th>Error</th></tr></thead>
                    <tbody>{error_rows}</tbody>
                </table>
                {screenshot_html}
            </div>"""
            )

    pass_rate = summary.get("passRate", 0)
    status_class = "pass" if pass_rate == 100 else "fail"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Power BI Visual Test Report</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; color: #333; }}
    h1 {{ margin-bottom: 4px; }}
    .header {{ background: #fff; padding: 20px 24px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .header .meta {{ color: #666; font-size: 14px; }}
    .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }}
    .stat {{ background: #fff; padding: 16px 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 140px; }}
    .stat .label {{ font-size: 13px; color: #666; text-transform: uppercase; }}
    .stat .value {{ font-size: 28px; font-weight: 700; margin-top: 4px; }}
    .stat .value.pass {{ color: #22863a; }}
    .stat .value.fail {{ color: #cb2431; }}
    .card {{ background: #fff; padding: 20px 24px; border-radius: 8px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .card.failed {{ border-left: 4px solid #cb2431; }}
    .card h3 {{ margin: 0 0 8px 0; }}
    .card .meta {{ color: #666; font-size: 13px; }}
    .card a {{ color: #0366d6; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px; }}
    th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }}
    th {{ background: #f9f9f9; font-weight: 600; }}
    .all-pass {{ text-align: center; padding: 40px; color: #22863a; }}
    .all-pass h2 {{ font-size: 24px; }}
</style>
</head>
<body>
<div class="header">
    <h1>Power BI Visual Test Report</h1>
    <p class="meta">Environment: {environment} | Generated: {generated_at}</p>
</div>
<div class="summary">
    <div class="stat"><div class="label">Reports</div><div class="value">{summary.get('totalReports', 0)}</div></div>
    <div class="stat"><div class="label">Total Pages</div><div class="value">{summary.get('totalPages', 0)}</div></div>
    <div class="stat"><div class="label">Passed</div><div class="value pass">{summary.get('passedPages', 0)}</div></div>
    <div class="stat"><div class="label">Failed</div><div class="value fail">{summary.get('failedPages', 0)}</div></div>
    <div class="stat"><div class="label">Pass Rate</div><div class="value {status_class}">{pass_rate}%</div></div>
</div>
"""

    if failed_sections:
        html += "<h2>Failed Pages</h2>\n" + "\n".join(failed_sections)
    else:
        html += '<div class="card all-pass"><h2>All pages passed visual validation</h2></div>'

    html += "\n</body>\n</html>"
    return html


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
        "passRate": (
            round(((total_pages - failed_pages) / total_pages) * 100, 2)
            if total_pages
            else 0
        ),
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

    # ---------------- CONSOLE SUMMARY ----------------
    log_to_console(
        f"\n{'='*60}\n"
        f"  SUMMARY: {summary['totalReports']} reports | "
        f"{summary['totalPages']} pages | "
        f"{summary['passedPages']} passed | "
        f"{summary['failedPages']} failed | "
        f"{summary['passRate']}% pass rate\n"
        f"{'='*60}",
        True,
    )

    if summary["failedPages"] > 0:
        log_to_console("\n  FAILED PAGES:", True)
        for report in all_results:
            report_name = report.get("reportName", "Unknown")
            for page_name, page_info in report.get("pages", {}).items():
                if page_info.get("errors"):
                    url = page_info.get("serviceUrl", "N/A")
                    error_count = len(page_info["errors"])
                    log_to_console(
                        f"    ✗ {report_name} / {page_name} ({error_count} error(s))\n"
                        f"      {url}",
                        True,
                    )
        log_to_console("", True)

    # ---------------- HTML REPORT ----------------
    html_report = TEST_RESULTS_DIR / "report.html"
    html_report.write_text(_generate_html_report(final_output), encoding="utf-8")
    log_to_console(f"[INFO] HTML report: {html_report}", True)

    # Auto-open in browser for local runs (skip in CI)
    if not os.environ.get("CI"):
        webbrowser.open(html_report.as_uri())

    # Optional: clean worker JSONs
    for f in TEST_RESULTS_DIR.glob("results_*.json"):
        f.unlink()
