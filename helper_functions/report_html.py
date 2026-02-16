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

        # Collect all failed entries (pages + bookmarks) for this report
        failed_entries = []
        for entry_key, entry_info in report.get("pages", {}).items():
            errors = entry_info.get("errors", {})
            if not errors:
                continue

            is_bookmark = "bookmarkDisplayName" in entry_info
            display_name = (
                f"Bookmark: {entry_info['bookmarkDisplayName']}" if is_bookmark else entry_key
            )

            service_url = entry_info.get("serviceUrl", "")
            duration = entry_info.get("duration", 0)

            # Find screenshot — bookmarks use bookmark_ prefix
            screenshot_html = ""
            if is_bookmark:
                bm_name = entry_key[len("bookmark:") :]
                glob_pattern = f"bookmark_{bm_name}_*.png"
            else:
                glob_pattern = f"{entry_key}_*.png"

            for png in results_dir.glob(glob_pattern):
                img_data = base64.b64encode(png.read_bytes()).decode("utf-8")
                screenshot_html = (
                    f'<img src="data:image/png;base64,{img_data}" alt="{display_name}" />'
                )
                break

            error_rows = "".join(
                f"<tr><td>{vid}</td><td>{msg}</td></tr>" for vid, msg in errors.items()
            )

            failed_entries.append(
                {
                    "display_name": display_name,
                    "service_url": service_url,
                    "duration": duration,
                    "error_rows": error_rows,
                    "screenshot_html": screenshot_html,
                    "is_bookmark": is_bookmark,
                }
            )

        if not failed_entries:
            continue

        failed_page_count = sum(1 for e in failed_entries if not e["is_bookmark"])
        failed_bm_count = sum(1 for e in failed_entries if e["is_bookmark"])

        meta_parts = []
        meta_parts.append(f"Report ID: {report_id}")
        if failed_page_count:
            meta_parts.append(
                f"{failed_page_count} failed page{'s' if failed_page_count != 1 else ''}"
            )
        if failed_bm_count:
            meta_parts.append(
                f"{failed_bm_count} failed bookmark{'s' if failed_bm_count != 1 else ''}"
            )

        # Build tiles for this report
        tiles = []
        for entry in failed_entries:
            tile_class = "page-tile bookmark-tile" if entry["is_bookmark"] else "page-tile"
            tiles.append(
                f"""<div class="{tile_class}">
                    <h4>{entry["display_name"]}</h4>
                    <p class="meta">Duration: {entry["duration"]:.0f}ms</p>
                    <p><a href="{entry["service_url"]}" target="_blank">Open in Power BI</a></p>
                    <table>
                        <thead><tr><th>Visual</th><th>Error</th></tr></thead>
                        <tbody>{entry["error_rows"]}</tbody>
                    </table>
                    {entry["screenshot_html"]}
                </div>"""
            )

        failed_sections.append(
            f"""
            <div class="card failed">
                <h3>{report_name}</h3>
                <p class="meta">{" | ".join(meta_parts)}</p>
                <div class="page-grid">
                    {"".join(tiles)}
                </div>
            </div>"""
        )

    pass_rate = summary.get("passRate", 0)
    status_class = "pass" if pass_rate == 100 else "fail"

    # Bookmark summary stats
    total_bookmarks = summary.get("totalBookmarks", 0)
    failed_bookmarks = summary.get("failedBookmarks", 0)

    bookmark_stats_html = ""
    if total_bookmarks > 0:
        bm_passed = total_bookmarks - failed_bookmarks
        bookmark_stats_html = f"""
    <div class="stat"><div class="label">Bookmarks</div><div class="value">{total_bookmarks}</div></div>
    <div class="stat"><div class="label">BM Passed</div><div class="value pass">{bm_passed}</div></div>
    <div class="stat"><div class="label">BM Failed</div><div class="value fail">{failed_bookmarks}</div></div>"""

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
    .card h3 {{ margin: 0 0 12px 0; }}
    .card .meta {{ color: #666; font-size: 13px; }}
    .card a {{ color: #0366d6; }}
    .page-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(480px, 1fr)); gap: 16px; margin-top: 12px; }}
    .page-tile {{ background: #fafafa; border: 1px solid #e1e4e8; border-radius: 6px; padding: 14px; }}
    .page-tile h4 {{ margin: 0 0 6px 0; font-size: 15px; }}
    .page-tile .meta {{ margin: 0 0 4px 0; }}
    .page-tile img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; margin-top: 8px; }}
    .bookmark-tile {{ border-left: 3px solid #0366d6; }}
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
    <div class="stat"><div class="label">Reports</div><div class="value">{summary.get("totalReports", 0)}</div></div>
    <div class="stat"><div class="label">Total Pages</div><div class="value">{summary.get("totalPages", 0)}</div></div>
    <div class="stat"><div class="label">Passed</div><div class="value pass">{summary.get("passedPages", 0)}</div></div>
    <div class="stat"><div class="label">Failed</div><div class="value fail">{summary.get("failedPages", 0)}</div></div>
    <div class="stat"><div class="label">Pass Rate</div><div class="value {status_class}">{pass_rate}%</div></div>{bookmark_stats_html}
</div>
"""

    if failed_sections:
        html += "<h2>Failed Reports</h2>\n" + "\n".join(failed_sections)
    else:
        html += '<div class="card all-pass"><h2>All pages and bookmarks passed visual validation</h2></div>'

    html += "\n</body>\n</html>"
    return html
