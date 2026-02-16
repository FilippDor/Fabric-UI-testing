"""Generate a standalone HTML report with failed pages and embedded screenshots."""

import base64
from pathlib import Path


def generate_html_report(final_output: dict, results_dir: Path) -> str:
    reports = final_output.get("reports", [])
    summary = final_output.get("summary", {})
    generated_at = final_output.get("generatedAt", "")
    environment = final_output.get("environment", "")

    failed_sections = []
    for report in reports:
        report_name = report.get("reportName", "Unknown")
        report_id = report.get("reportId", "")

        for page_name, page_info in report.get("pages", {}).items():
            errors = page_info.get("errors", {})
            if not errors:
                continue

            service_url = page_info.get("serviceUrl", "")
            duration = page_info.get("duration", 0)

            screenshot_html = ""
            for png in results_dir.glob(f"{page_name}_*.png"):
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
