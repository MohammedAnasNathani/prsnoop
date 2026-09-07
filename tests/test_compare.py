"""Compare subcommand tests via monkeypatched fetch."""
from __future__ import annotations

import pytest

from prsnoop import cli


@pytest.fixture
def two_users(monkeypatch, sample_prs, sample_reviews, sample_issues, now):
    """user_a gets the fixture activity; user_b gets a scaled-down copy."""

    def fake_fetch(client, user, days, include_reviews, org=None, since=None, until=None):
        if user == "alice":
            return sample_prs, [], sample_issues, True
        fewer = [sample_prs[0]]
        return fewer, [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)


class TestCompare:
    def test_table_output(self, two_users, capsys):
        code = cli.run(["compare", "alice", "bob", "--days", "30"])
        captured = capsys.readouterr()
        assert code == 0
        out = captured.out
        assert "alice vs bob" in out
        assert "pull requests" in out
        assert "merge rate" in out
        assert "longest streak" in out

    def test_markdown_output(self, two_users, capsys):
        code = cli.run(["compare", "alice", "bob", "--format", "markdown"])
        captured = capsys.readouterr()
        assert code == 0
        out = captured.out
        assert out.startswith("# alice vs bob")
        assert "| Metric | alice | bob |" in out
        assert "| pull requests | 3 | 1 |" in out

    def test_both_sides_shown(self, two_users, capsys):
        cli.run(["compare", "alice", "bob"])
        out = capsys.readouterr().out
        assert "alice" in out and "bob" in out
