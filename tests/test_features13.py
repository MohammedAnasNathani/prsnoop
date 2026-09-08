"""Tests for 1.3 features: trend deltas, sparkline, org pulse, compare formats."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from prsnoop.cli import _previous_window, run
from prsnoop.models import Activity, DayActivity, PRRecord
from prsnoop.org import fetch_org_pulse
from prsnoop.render import (
    _sparkline,
    render_html,
    render_json,
    render_markdown,
    render_org_markdown,
    render_org_table,
    render_table,
)
from prsnoop.stats import build_activity, build_trend


def _pr(days_ago: float, merged: bool = True, adds: int = 10) -> PRRecord:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    merged_at = created + timedelta(days=0.1) if merged else None
    return PRRecord(
        repo="acme/app", number=1, title="x", url="https://example.com",
        state="merged" if merged else "open", created_at=created,
        merged_at=merged_at, additions=adds, deletions=1, changed_files=1,
    )


def _activity(prs: list[PRRecord]) -> Activity:
    return build_activity("tester", prs, [], [], window_days=30)


def test_build_trend_direction_and_pct():
    cur = _activity([_pr(1), _pr(2), _pr(3)])
    prev = _activity([_pr(10), _pr(11)])
    deltas = build_trend(cur.stats, prev.stats)
    by_key = {d.key: d for d in deltas}
    assert by_key["prs_authored"].delta == 1
    assert by_key["prs_authored"].direction == 1
    assert by_key["prs_authored"].improved is True
    assert by_key["prs_authored"].pct == 50.0


def test_build_trend_zero_previous_has_no_pct():
    cur = _activity([_pr(1)])
    prev = _activity([])
    deltas = build_trend(cur.stats, prev.stats)
    by_key = {d.key: d for d in deltas}
    assert by_key["prs_authored"].previous == 0
    assert by_key["prs_authored"].pct is None
    assert by_key["prs_authored"].improved is True


def test_build_trend_lower_is_better_median():
    cur = _activity([_pr(1)])
    prev = _activity([_pr(10)])
    # same 0.1d merge time in both windows: flat, and flat is not improved
    deltas = build_trend(cur.stats, prev.stats)
    median = [d for d in deltas if d.key == "median_days_to_merge"][0]
    assert median.direction == 0
    assert median.improved is False


def test_build_trend_skips_missing_median():
    cur = _activity([_pr(1, merged=False)])
    prev = _activity([_pr(10)])
    deltas = build_trend(cur.stats, prev.stats)
    assert all(d.key != "median_days_to_merge" for d in deltas)


def test_table_shows_trend_section():
    cur = _activity([_pr(1), _pr(2)])
    prev = _activity([_pr(10)])
    cur.trend = build_trend(cur.stats, prev.stats)
    out = render_table(cur)
    assert "Trend vs previous window" in out
    assert "pull requests" in out


def test_table_hides_trend_when_empty():
    out = render_table(_activity([_pr(1)]))
    assert "Trend" not in out


def test_markdown_trend_table():
    cur = _activity([_pr(1), _pr(2)])
    prev = _activity([_pr(10)])
    cur.trend = build_trend(cur.stats, prev.stats)
    out = render_markdown(cur)
    assert "## Trend vs previous window" in out
    assert "| pull requests | 1 | 2 |" in out


def test_json_includes_trend():
    cur = _activity([_pr(1), _pr(2)])
    prev = _activity([_pr(10)])
    cur.trend = build_trend(cur.stats, prev.stats)
    import json

    payload = json.loads(render_json(cur))
    assert payload["trend"][0]["key"] == "prs_authored"
    assert "improved" in payload["trend"][0]


def test_html_trend_arrows_and_chart():
    cur = _activity([_pr(1), _pr(2), _pr(5)])
    prev = _activity([_pr(10)])
    cur.trend = build_trend(cur.stats, prev.stats)
    out = render_html(cur)
    assert '<svg class="chart"' in out
    assert "trend-" in out
    assert "<title>" in out  # svg bar tooltips


def test_html_without_day_activity_has_no_chart():
    out = render_html(_activity([]))
    assert '<svg class="chart"' not in out


# ---------------------------------------------------------------- sparkline


def test_sparkline_empty():
    assert _sparkline([]) == ""


def test_sparkline_scales_levels():
    days = [
        DayActivity("2026-01-01", prs=0, merged=0, issues=0, reviews=0),
        DayActivity("2026-01-02", prs=1, merged=0, issues=0, reviews=0),
        DayActivity("2026-01-03", prs=10, merged=0, issues=0, reviews=0),
    ]
    spark = _sparkline(days)
    assert spark[0] == "."
    assert spark[2] == "#"
    assert len(spark) == 3


def test_sparkline_buckets_long_windows():
    days = [
        DayActivity(f"2026-01-{i+1:02d}", prs=1, merged=0, issues=0, reviews=0)
        for i in range(90)
    ]
    spark = _sparkline(days, width=30)
    assert len(spark) == 30
    assert "." not in spark  # every bucket has activity


# ------------------------------------------------------------------ org pulse


class _OrgFakeClient:
    """FakeClient-style stub for org searches."""

    def __init__(self, items: list[dict]) -> None:
        self.items = items

    def paginate(self, path: str, params: dict | None = None) -> list[dict]:
        return self.items

    def get(self, path: str) -> object:
        raise AssertionError("org pulse must not enrich per PR")


def _org_item(number: int, merged: bool, author: str) -> dict:
    closed = "2026-08-20T10:00:00Z" if merged else None
    state = "closed" if merged else "open"
    return {
        "number": number,
        "title": f"pr {number}",
        "html_url": f"https://github.com/acme/app/pull/{number}",
        "state": state,
        "created_at": "2026-08-15T10:00:00Z",
        "closed_at": closed,
        "user": {"login": author},
        "repository_url": "https://api.github.com/repos/acme/app",
        "pull_request": {
            "merged_at": "2026-08-20T10:00:00Z" if merged else None,
        },
    }


def test_fetch_org_pulse_counts():
    items = [
        _org_item(1, merged=True, author="alice"),
        _org_item(2, merged=True, author="bob"),
        _org_item(3, merged=False, author="alice"),
        _org_item(4, merged=False, author="carol"),
    ]
    prs, pulse = fetch_org_pulse(
        _OrgFakeClient(items), "acme", days=30,
        since="2026-08-01", until="2026-08-31",
    )
    assert pulse.org == "acme"
    assert pulse.prs_opened == 4
    assert pulse.prs_merged == 2
    assert pulse.prs_open == 2
    assert pulse.authors == 3
    assert pulse.repos == 1
    assert pulse.top_authors[0] == ("alice", 2)
    assert pulse.median_days_to_merge is not None
    assert len(pulse.day_counts) == 1


def test_org_renderers():
    items = [_org_item(1, merged=True, author="alice")]
    prs, pulse = fetch_org_pulse(
        _OrgFakeClient(items), "acme", days=30,
        since="2026-08-01", until="2026-08-31",
    )
    table = render_org_table(prs, pulse)
    md = render_org_markdown(prs, pulse)
    assert "prsnoop org | acme" in table
    assert "Top authors" in table
    assert "# Org pulse: acme" in md
    assert "## Top authors" in md
    assert "[alice](https://github.com/alice)" in md


def test_org_pulse_to_dict_roundtrip():
    import json

    items = [_org_item(1, merged=True, author="alice")]
    _prs, pulse = fetch_org_pulse(
        _OrgFakeClient(items), "acme", days=30,
        since="2026-08-01", until="2026-08-31",
    )
    payload = json.loads(json.dumps(pulse.to_dict()))
    assert payload["org"] == "acme"
    assert payload["top_authors"][0]["author"] == "alice"


# ----------------------------------------------------------- cli internals

from prsnoop import cli  # noqa: E402


class _CompareFetch:
    """Offline stand-in returning fixture records for any user."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, client, user, days, include_reviews, org=None,
                 since=None, until=None):
        self.calls.append(user)
        return [_pr(1), _pr(2)], [], [], True


def test_previous_window_relative():
    since, until = _previous_window(None, None, days=30)
    # fetch uses created:>=since, so the current window is [today-30, today]
    # and the previous window is [today-60, today-31], same size.
    today = datetime.now(timezone.utc).date()
    assert since == (today - timedelta(days=60)).isoformat()
    assert until == (today - timedelta(days=31)).isoformat()


def test_previous_window_absolute():
    since, until = _previous_window("2026-08-01", "2026-08-31", days=30)
    assert since == "2026-07-01"
    assert until == "2026-07-31"


def test_compare_csv_format(capsys, monkeypatch):
    monkeypatch.setattr(cli, "fetch_user_activity", _CompareFetch())
    code = cli.run(["compare", "antfu", "simonw", "--days", "7", "-f", "csv"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("metric,antfu,simonw")
    assert "pull requests" in out


def test_compare_json_format(capsys, monkeypatch):
    import json as json_mod

    monkeypatch.setattr(cli, "fetch_user_activity", _CompareFetch())
    code = cli.run(["compare", "antfu", "simonw", "--days", "7", "-f", "json"])
    payload = json_mod.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["users"] == ["antfu", "simonw"]
    assert any(m["metric"] == "pull requests" for m in payload["metrics"])


def test_org_cli_table(capsys, monkeypatch):
    """prsnoop org runs offline against a stubbed fetch_org_pulse."""
    import prsnoop.org as org_mod

    fake_items = [
        {
            "number": 1, "title": "one", "state": "closed", "html_url": "u1",
            "created_at": "2026-08-15T10:00:00Z",
            "closed_at": "2026-08-20T10:00:00Z",
            "user": {"login": "alice"},
            "repository_url": "https://api.github.com/repos/acme/app",
            "pull_request": {"merged_at": "2026-08-20T10:00:00Z"},
        }
    ]
    prs, pulse = fetch_org_pulse(
        _OrgFakeClient(fake_items), "acme", days=30,
        since="2026-08-01", until="2026-08-31",
    )

    def fake_pulse(client, org, days=30, since=None, until=None):
        return prs, pulse

    monkeypatch.setattr(org_mod, "fetch_org_pulse", fake_pulse)
    code = cli.run(["org", "acme", "--days", "30"])
    out = capsys.readouterr().out
    assert code == 0
    assert "prsnoop org | acme" in out
    assert "alice" in out


def test_org_requires_org_name(capsys):
    # argparse exits 2 for a missing required positional
    with pytest.raises(SystemExit) as exc:
        run(["org", "--days", "5"])
    assert exc.value.code == 2
