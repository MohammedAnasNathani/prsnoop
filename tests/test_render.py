"""Renderer output tests: every format must be complete, valid, and ASCII."""
from __future__ import annotations

import csv
import io
import json

from prsnoop.render import (
    render_csv,
    render_html,
    render_json,
    render_markdown,
    render_table,
)
from prsnoop.stats import build_activity


class TestTable:
    def test_shows_headline_numbers(self, activity):
        out = render_table(activity)
        assert "octocat" in out
        assert "Pull requests      3" in out
        assert "Drafts             0" in out
        assert "Merge rate         67%" in out
        assert "aio-libs/yarl#1828" in out

    def test_shows_streaks_and_languages(self, activity):
        out = render_table(activity)
        assert "Streaks" in out
        assert "longest" in out and "current" in out
        assert "Languages" in out

    def test_daily_activity_bars(self, activity):
        out = render_table(activity)
        assert "Daily activity" in out
        assert "2026-07-10" in out  # PR created that day

    def test_pure_ascii(self, activity):
        out = render_table(activity)
        out.encode("ascii")  # raises UnicodeEncodeError if not ASCII

    def test_empty_activity(self, now):
        out = render_table(build_activity("nobody", [], [], [], now=now))
        assert "(none)" in out


class TestMarkdown:
    def test_summary_table(self, activity):
        out = render_markdown(activity)
        assert out.startswith("# Contribution report: octocat")
        assert "| Pull requests | 3 |" in out
        assert "| Drafts | 0 |" in out
        assert "| Merge rate | 67% |" in out
        assert "[aio-libs/yarl#1828](https://github.com/aio-libs/yarl/pull/1828)" in out

    def test_has_all_sections(self, activity):
        out = render_markdown(activity)
        assert "## Top repositories" in out
        assert "## Languages" in out
        assert "## Daily activity" in out
        assert "## Pull requests" in out
        assert "## Reviews given" in out
        assert "## Issues opened" in out

    def test_p90_and_streaks(self, activity):
        out = render_markdown(activity)
        assert "P90 time to merge" in out
        assert "| Longest streak |" in out
        assert "| Current streak |" in out

    def test_pure_ascii(self, activity):
        render_markdown(activity).encode("ascii")


class TestHTML:
    def test_valid_structure(self, activity):
        out = render_html(activity)
        assert out.startswith("<!doctype html>")
        assert out.rstrip().endswith("</html>")
        assert "<title>prsnoop | octocat</title>" in out
        assert 'href="https://github.com/aio-libs/yarl/pull/1828"' in out

    def test_daily_activity_bars_present(self, activity):
        out = render_html(activity)
        assert "Daily activity" in out

    def test_escapes_titles(self, activity):
        activity.prs[0].title = 'XSS <script>alert("boom")</script>'
        out = render_html(activity)
        assert "<script>alert" not in out
        assert "&lt;script&gt;" in out


class TestCSV:
    def test_rows_and_header(self, activity):
        out = render_csv(activity)
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0] == [
            "repo", "number", "title", "state", "created_at", "merged_at",
            "additions", "deletions", "changed_files", "labels", "comments",
            "language", "days_to_merge", "url",
        ]
        assert len(rows) == 4  # header + 3 PRs
        yarl = next(r for r in rows[1:] if r[0] == "aio-libs/yarl")
        assert yarl[3] == "merged"
        assert yarl[6] == "42"

    def test_empty_csv(self, now):
        out = render_csv(build_activity("nobody", [], [], [], now=now))
        rows = list(csv.reader(io.StringIO(out)))
        assert len(rows) == 1  # just the header


class TestJSON:
    def test_roundtrip(self, activity):
        data = json.loads(render_json(activity))
        assert data["user"] == "octocat"
        assert data["stats"]["prs_authored"] == 3
        assert data["stats"]["prs_merged"] == 2
        assert len(data["prs"]) == 3

    def test_new_stats_fields(self, activity):
        data = json.loads(render_json(activity))
        s = data["stats"]
        assert s["active_days"] >= 1
        assert s["longest_streak_days"] >= 1
        assert isinstance(s["day_activity"], list)
        assert s["day_activity"][0]["date"] == "2026-07-05"
        assert s["languages"][0]["language"] in {"Python", "Unknown"}
        assert "p90_days_to_merge" in s

    def test_dates_are_iso_z(self, activity):
        data = json.loads(render_json(activity))
        assert data["prs"][0]["created_at"].endswith("Z")
