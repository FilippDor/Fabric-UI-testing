"""Unit tests for helper_functions.report_html (no credentials required)."""

import pytest

from helper_functions.report_html import generate_html_report


@pytest.fixture
def sample_output_all_pass():
    return {
        "environment": "prod",
        "generatedAt": "2026-01-15T12:00:00Z",
        "summary": {
            "totalReports": 2,
            "totalPages": 5,
            "failedPages": 0,
            "passedPages": 5,
            "passRate": 100,
        },
        "reports": [
            {
                "reportId": "r1",
                "reportName": "Sales Report",
                "pages": {
                    "page1": {
                        "errors": {},
                        "duration": 1200,
                        "serviceUrl": "https://example.com/p1",
                    },
                    "page2": {
                        "errors": {},
                        "duration": 800,
                        "serviceUrl": "https://example.com/p2",
                    },
                },
            }
        ],
    }


@pytest.fixture
def sample_output_with_failures():
    return {
        "environment": "prod",
        "generatedAt": "2026-01-15T12:00:00Z",
        "summary": {
            "totalReports": 1,
            "totalPages": 2,
            "failedPages": 1,
            "passedPages": 1,
            "passRate": 50.0,
        },
        "reports": [
            {
                "reportId": "r1",
                "reportName": "Broken Report",
                "pages": {
                    "page1": {
                        "errors": {},
                        "duration": 1200,
                        "serviceUrl": "https://example.com/p1",
                    },
                    "page2": {
                        "errors": {"visual-abc": "Rendering timeout"},
                        "duration": 15000,
                        "serviceUrl": "https://example.com/p2",
                    },
                },
            }
        ],
    }


class TestGenerateHtmlReport:
    def test_returns_valid_html(self, sample_output_all_pass, tmp_path):
        html = generate_html_report(sample_output_all_pass, tmp_path)

        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_title(self, sample_output_all_pass, tmp_path):
        html = generate_html_report(sample_output_all_pass, tmp_path)

        assert "Power BI Visual Test Report" in html

    def test_contains_environment(self, sample_output_all_pass, tmp_path):
        html = generate_html_report(sample_output_all_pass, tmp_path)

        assert "prod" in html

    def test_contains_summary_stats(self, sample_output_all_pass, tmp_path):
        html = generate_html_report(sample_output_all_pass, tmp_path)

        assert "100%" in html

    def test_all_pass_shows_success_message(self, sample_output_all_pass, tmp_path):
        html = generate_html_report(sample_output_all_pass, tmp_path)

        assert "All pages and bookmarks passed" in html

    def test_failures_shown(self, sample_output_with_failures, tmp_path):
        html = generate_html_report(sample_output_with_failures, tmp_path)

        assert "Broken Report" in html
        assert "Rendering timeout" in html
        assert "visual-abc" in html
        assert "Failed Reports" in html

    def test_failure_includes_service_url(self, sample_output_with_failures, tmp_path):
        html = generate_html_report(sample_output_with_failures, tmp_path)

        assert "https://example.com/p2" in html

    def test_pass_rate_shown(self, sample_output_with_failures, tmp_path):
        html = generate_html_report(sample_output_with_failures, tmp_path)

        assert "50.0%" in html

    def test_multiple_failed_pages_grouped_in_one_card(self, tmp_path):
        """Multiple failed pages in one report should appear in a single card with a grid."""
        data = {
            "environment": "prod",
            "generatedAt": "2026-01-15T12:00:00Z",
            "summary": {
                "totalReports": 1,
                "totalPages": 3,
                "failedPages": 2,
                "passedPages": 1,
                "passRate": 33.33,
            },
            "reports": [
                {
                    "reportId": "r1",
                    "reportName": "Multi-Fail Report",
                    "pages": {
                        "page1": {
                            "errors": {},
                            "duration": 500,
                            "serviceUrl": "https://example.com/p1",
                        },
                        "page2": {
                            "errors": {"v1": "Error A"},
                            "duration": 10000,
                            "serviceUrl": "https://example.com/p2",
                        },
                        "page3": {
                            "errors": {"v2": "Error B"},
                            "duration": 12000,
                            "serviceUrl": "https://example.com/p3",
                        },
                    },
                }
            ],
        }

        html = generate_html_report(data, tmp_path)

        # One report card, not two separate ones
        assert html.count("Multi-Fail Report") == 1
        assert "2 failed pages" in html
        # Both pages present inside the grid
        assert "page2" in html
        assert "page3" in html
        assert "Error A" in html
        assert "Error B" in html
        assert "page-grid" in html

    def test_bookmark_failure_shown_with_prefix(self, tmp_path):
        """Failed bookmark entries should display with 'Bookmark:' prefix."""
        data = {
            "environment": "prod",
            "generatedAt": "2026-01-15T12:00:00Z",
            "summary": {
                "totalReports": 1,
                "totalPages": 1,
                "failedPages": 0,
                "passedPages": 1,
                "passRate": 100,
                "totalBookmarks": 1,
                "failedBookmarks": 1,
            },
            "reports": [
                {
                    "reportId": "r1",
                    "reportName": "Bookmark Report",
                    "pages": {
                        "page1": {
                            "errors": {},
                            "duration": 1000,
                            "serviceUrl": "https://example.com/p1",
                        },
                        "bookmark:bm1": {
                            "errors": {"unknown": "Render failed"},
                            "duration": 15000,
                            "bookmarkDisplayName": "Q1 Filter",
                            "serviceUrl": "https://example.com/p1?bookmarkGuid=bm1",
                        },
                    },
                }
            ],
        }

        html = generate_html_report(data, tmp_path)

        assert "Bookmark: Q1 Filter" in html
        assert "Render failed" in html
        assert "bookmark-tile" in html
        assert "1 failed bookmark" in html

    def test_mixed_page_and_bookmark_failures(self, tmp_path):
        """Both page and bookmark failures in one report should appear in one card."""
        data = {
            "environment": "prod",
            "generatedAt": "2026-01-15T12:00:00Z",
            "summary": {
                "totalReports": 1,
                "totalPages": 2,
                "failedPages": 1,
                "passedPages": 1,
                "passRate": 50.0,
                "totalBookmarks": 1,
                "failedBookmarks": 1,
            },
            "reports": [
                {
                    "reportId": "r1",
                    "reportName": "Mixed Failures",
                    "pages": {
                        "page1": {
                            "errors": {"v1": "Page error"},
                            "duration": 15000,
                            "serviceUrl": "https://example.com/p1",
                        },
                        "page2": {
                            "errors": {},
                            "duration": 500,
                            "serviceUrl": "https://example.com/p2",
                        },
                        "bookmark:bm-sales": {
                            "errors": {"unknown": "Bookmark render failed"},
                            "duration": 15000,
                            "bookmarkDisplayName": "Sales View",
                            "serviceUrl": "https://example.com/p1?bookmarkGuid=bm-sales",
                        },
                    },
                }
            ],
        }

        html = generate_html_report(data, tmp_path)

        assert html.count("Mixed Failures") == 1
        assert "1 failed page" in html
        assert "1 failed bookmark" in html
        assert "Page error" in html
        assert "Bookmark: Sales View" in html
        assert "Bookmark render failed" in html

    def test_bookmark_summary_stats_shown(self, tmp_path):
        """Bookmark stats should appear in the summary bar when bookmarks exist."""
        data = {
            "environment": "prod",
            "generatedAt": "2026-01-15T12:00:00Z",
            "summary": {
                "totalReports": 1,
                "totalPages": 1,
                "failedPages": 0,
                "passedPages": 1,
                "passRate": 100,
                "totalBookmarks": 3,
                "failedBookmarks": 1,
            },
            "reports": [],
        }

        html = generate_html_report(data, tmp_path)

        assert "Bookmarks" in html
        assert "BM Passed" in html
        assert "BM Failed" in html

    def test_no_bookmark_stats_when_zero(self, sample_output_all_pass, tmp_path):
        """Bookmark stats should not appear when there are no bookmarks."""
        html = generate_html_report(sample_output_all_pass, tmp_path)

        assert "Bookmarks" not in html
        assert "BM Passed" not in html
