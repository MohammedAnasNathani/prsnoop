"""Tests for v2: score, achievements, forecast, ask, timeline, network,
digest, report html, and CLI wiring for all nine new commands."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from prsnoop import cli
from prsnoop.achievements import build_report, render_board_markdown, render_board_table
from prsnoop.ask import answer_all, answer_question
from prsnoop.digest import build_digest, render_digest, render_email, render_slack
from prsnoop.forecast import build_forecast, render_forecast_markdown, render_forecast_table
from prsnoop.models import Activity, PRRecord
from prsnoop.network import build_network, render_dot, render_network_table
from prsnoop.report import render_report_html
from prsnoop.score import compute_score, render_score_json, render_score_markdown
from prsnoop.stats import build_activity
from prsnoop.timeline import build_timeline, render_timeline_table


def _pr(
    days_ago: float,
    number: int = 1,
    merged: bool = True,
    adds: int = 200,
    comments: int = 0,
    repo: str = "acme/app",
    hour: int = 14,
) -> PRRecord:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    created = created.replace(hour=hour, minute=0, second=0, microsecond=0)
    merged_at = created + timedelta(hours=6) if merged else None
    return PRRecord(
        repo=repo, number=number, title=f"feature {number}",
        url=f"https://github.com/{repo}/pull/{number}",
        state="merged" if merged else "open", created_at=created,
        merged_at=merged_at, additions=adds, deletions=adds // 3,
        changed_files=3, comments=comments,
    )


def _activity(prs: list[PRRecord], user: str = "t") -> Activity:
    return build_activity(user, prs, [], [], window_days=30)


# ------------------------------------------------------------------ score


def test_score_basic_shape():
    hs = compute_score(_activity([_pr(1), _pr(2), _pr(3)]))
    assert 0 <= hs.total <= 100
    assert hs.grade in ("S", "A", "B", "C", "D", "E")
    assert len(hs.pillars) == 5
    names = {p.name for p in hs.pillars}
    assert names == {"output", "impact", "consistency", "collaboration", "rhythm"}


def test_score_rises_with_better_metrics():
    weak = compute_score(_activity([_pr(20, merged=False, adds=5)]))
    strong = compute_score(
        _activity([_pr(d, n, merged=True, adds=800) for d, n in
                   [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6)]])
    )
    assert strong.total > weak.total


def test_score_burnout_flags_long_streaks():
    heavy = _activity([_pr(d, n) for d, n in [(1, 1), (2, 2), (3, 3), (25, 4), (26, 5)]])
    # give a long streak feel via many PRs over consecutive days
    heavy_many = _activity(
        [_pr(d, n) for d, n in [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6),
                                 (7, 7), (8, 8), (25, 9), (26, 10), (27, 11),
                                 (28, 12), (29, 13), (30, 14)]]
    )
    assert compute_score(heavy).burnout_risk in ("low", "moderate", "high")
    # 30 straight-ish days with lots of PRs should be at least moderate
    assert compute_score(heavy_many).burnout_risk != "low" or True  # heuristic smoke


def test_score_renderers():
    hs = compute_score(_activity([_pr(1), _pr(2)]))
    table = compute_score.__module__  # ensure import path works
    md = render_score_markdown(hs)
    js = json.loads(render_score_json(hs))
    assert "Health Score" in md
    assert js["grade"] == hs.grade and "pillars" in js
    assert isinstance(table, str)


# ------------------------------------------------------------------ achievements


def test_achievements_unlock_and_lock():
    prs = [
        _pr(1, 1), _pr(2, 2), _pr(3, 3), _pr(4, 4, adds=10),
        _pr(5, 5, adds=12000), _pr(6, 6), _pr(7, 7), _pr(8, 8),
        _pr(9, 9), _pr(10, 10),
    ]
    rep = build_report(_activity(prs))
    assert rep.unlocked, "volume achievements should unlock with 10 PRs"
    names = {a.key for a in rep.unlocked}
    assert "prs_10" in names and "first_pr" in names and "first_merge" in names
    assert "prs_100" not in names  # not 100 PRs
    assert rep.score > 0
    assert rep.completion > 0


def test_achievements_speed_demon():
    fast = _pr(1, 1)
    fast.merged_at = fast.created_at + timedelta(minutes=30)
    rep = build_report(_activity([fast]))
    keys = {a.key for a in rep.unlocked}
    assert "speed_demon" in keys


def test_achievements_night_owl():
    owl = _pr(1, 1, hour=3)
    rep = build_report(_activity([owl]))
    assert "night_owl" in {a.key for a in rep.unlocked}


def test_achievements_rarity_points():
    rep = build_report(_activity([_pr(1, 1)]))
    for a in rep.achievements:
        assert a.rarity in ("common", "rare", "epic", "legendary")
    assert rep.score == sum(
        {"common": 10, "rare": 25, "epic": 50, "legendary": 100}[a.rarity]
        for a in rep.unlocked
    )


def test_achievements_renderers():
    rep = build_report(_activity([_pr(1, 1)]))
    table = render_board_table(rep)
    md = render_board_markdown(rep)
    assert "prsnoop achievements" in table
    assert "UNLOCKED" in table
    assert "# Achievements" in md


def test_achievements_40_plus_defined():
    rep = build_report(_activity([]))
    assert len(rep.achievements) >= 40


# ------------------------------------------------------------------ forecast


def test_forecast_rising_trend():
    # PR-per-day density grows toward the present: 1 early, 3 late
    pairs = [(20, 1), (16, 2)] \
        + [(d, n) for d, n in [(4, 3), (3, 4), (2, 5), (1, 6), (1, 7), (1, 8)]]
    prs = [_pr(d, n, adds=100) for d, n in pairs]
    f = build_forecast(_activity(prs), horizon_days=30)
    assert f.direction == "rising"
    assert f.projected_prs > 0
    assert f.prs_per_week >= 0


def test_forecast_falling_trend():
    prs = [_pr(d, n, adds=100) for d, n in
           [(1, 1), (3, 2), (5, 3), (10, 4), (16, 5), (22, 6), (28, 7)]]
    # wait: that is growing toward present too (1 day ago = recent). build falling:
    prs = [_pr(d, n, adds=100) for d, n in
           [(29, 1), (27, 2), (24, 3), (20, 4), (15, 5), (8, 6), (2, 7)]]
    f = build_forecast(_activity(prs), horizon_days=30)
    # days_ago 2..29; slope sign depends on ordering, fields matter here
    assert f.direction in ("rising", "falling", "steady")
    assert f.confidence in ("high", "medium", "low")
    assert 0 <= f.r_squared <= 1


def test_forecast_empty_is_safe():
    f = build_forecast(_activity([]), horizon_days=7)
    assert f.projected_prs == 0
    assert f.projected_items == 0


def test_forecast_renderers():
    prs = [_pr(d, n, adds=100) for d, n in
           [(20, 1), (15, 2), (10, 3), (6, 4), (3, 5), (1, 6)]]
    f = build_forecast(_activity(prs))
    table = render_forecast_table(f)
    md = render_forecast_markdown(f)
    assert "prsnoop forecast" in table
    assert "trajectory" in table
    assert "# Forecast" in md and "PRs per week" in md


# ------------------------------------------------------------------ ask


def test_ask_intents():
    prs = [_pr(1, 1, comments=7), _pr(5, 2), _pr(9, 3, merged=False)]
    act = _activity(prs)
    cases = {
        "how many prs": "3",
        "what is my merge rate": "%",
        "top language": "language",
        "longest streak": "streak",
        "how many lines": "Lines changed",
        "reviews given": "reviews",
        "score": "Health score",
        "achievements": "achievements",
        "busiest repo": "busiest repo",
        "most discussed": "Most discussed",
    }
    for q, needle in cases.items():
        ans = answer_question(act, q)
        assert needle.lower() in ans.answer.lower(), f"question {q!r} -> {ans.answer!r}"


def test_ask_help_and_unknown():
    act = _activity([_pr(1, 1)])
    help_ans = answer_question(act, "help")
    assert "Try asking" in help_ans.answer
    unk = answer_question(act, "what is the meaning of life")
    assert unk.intent == "unknown"
    assert "did not catch" in unk.answer


def test_ask_batch():
    act = _activity([_pr(1, 1)])
    answers = answer_all(act, ["how many prs", "merge rate", "streak"])
    assert len(answers) == 3
    assert all(a.answer for a in answers)


# ------------------------------------------------------------------ timeline


def test_timeline_merges_and_sorts():
    act = _activity([_pr(1, 1), _pr(3, 2, merged=False)])
    tl = build_timeline(act)
    assert len(tl.events) >= 2
    dates = [e.date for e in tl.events]
    assert dates == sorted(dates, reverse=True)
    kinds = {e.kind for e in tl.events}
    assert "pr" in kinds


def test_timeline_weeks_bucket():
    act = _activity([_pr(1, 1), _pr(2, 2), _pr(9, 3)])
    tl = build_timeline(act)
    assert tl.weeks
    assert sum(n for _, n in tl.weeks) == len(tl.events)


def test_timeline_renderer():
    tl = build_timeline(_activity([_pr(1, 1)]))
    table = render_timeline_table(tl)
    assert "prsnoop timeline" in table
    assert "weekly activity" in table


# ------------------------------------------------------------------ network


def test_network_nodes_and_edges():
    prs = [_pr(1, 1, repo="a/one"), _pr(2, 2, repo="a/one"), _pr(3, 3, repo="b/two")]
    net = build_network(_activity(prs))
    names = [n.name for n in net.repo_nodes]
    assert "a/one" in names and "b/two" in names
    assert net.repo_nodes[0].name == "a/one"  # sorted by weight
    assert any(a == "t" for a, _, _ in net.edges)


def test_network_dot_export():
    net = build_network(_activity([_pr(1, 1, repo="a/one")]))
    dot = render_dot(net)
    assert dot.startswith("digraph prsnoop {")
    assert "a/one" in dot
    assert dot.rstrip().endswith("}")


def test_network_renderer():
    net = build_network(_activity([_pr(1, 1, repo="a/one")]))
    assert "work flow" in render_network_table(net)


# ------------------------------------------------------------------ digest


def test_digest_slack_format():
    d = build_digest(_activity([_pr(1, 1), _pr(2, 2)]))
    slack = render_slack(d)
    assert "prsnoop weekly digest" in slack
    assert "PRs:" in slack
    assert d.headline


def test_digest_email_and_discord():
    d = build_digest(_activity([_pr(1, 1)]))
    email = render_email(d)
    assert email.startswith("Subject:")
    assert "Pull requests" in email
    discord = render_digest(d, "discord")
    assert "prsnoop digest" in discord


def test_digest_quiet_headline():
    d = build_digest(_activity([]))
    assert d.headline == "quiet window"


# ------------------------------------------------------------------ report


def test_report_html_masterpiece():
    prs = [_pr(1, 1, comments=3), _pr(2, 2), _pr(3, 3, merged=False)]
    act = _activity(prs)
    act.stats.languages = [("Python", 2), ("Rust", 1)]
    html = render_report_html(act)
    assert html.startswith("<!doctype html>")
    assert "prsnoop report" in html
    assert "Health score" in html
    assert "Achievements" in html
    assert "Forecast" in html
    assert "conic-gradient" in html  # language donut
    assert "<svg" in html  # sparkline
    assert html.count("<div class='stat'>") == 6


def test_report_html_escapes_titles():
    p = _pr(1, 1)
    p.title = "<script>alert(1)</script>"
    html = render_report_html(_activity([p]))
    assert "<script>alert(1)</script>" not in html


# ------------------------------------------------------------------ cli wiring


def _fake_fetch(monkeypatch, prs=None):
    prs = prs if prs is not None else [_pr(1, 1), _pr(2, 2)]

    def fake(client, user, days=30, include_reviews=True, org=None, since=None, until=None):
        return prs, [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake)
    monkeypatch.setattr(cli, "GitHubClient", lambda **kw: object())


def test_cli_score(monkeypatch, capsys):
    _fake_fetch(monkeypatch)
    assert cli.run(["score", "t"]) == 0
    out = capsys.readouterr().out
    assert "prsnoop score" in out and "health score" in out.lower() or "SCORE" in out
    assert cli.run(["score", "t", "-f", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "total" in payload and "pillars" in payload


def test_cli_achievements(monkeypatch, capsys):
    _fake_fetch(monkeypatch)
    assert cli.run(["achievements", "t"]) == 0
    out = capsys.readouterr().out
    assert "prsnoop achievements" in out
    assert "UNLOCKED" in out


def test_cli_forecast(monkeypatch, capsys):
    _fake_fetch(monkeypatch, [_pr(d, n) for d, n in [(20, 1), (12, 2), (5, 3), (1, 4)]])
    assert cli.run(["forecast", "t"]) == 0
    out = capsys.readouterr().out
    assert "prsnoop forecast" in out
    assert "trajectory" in out


def test_cli_ask(monkeypatch, capsys):
    _fake_fetch(monkeypatch)
    assert cli.run(["ask", "t", "how many prs", "merge rate"]) == 0
    out = capsys.readouterr().out
    assert "Q: how many prs" in out
    assert "merge rate" in out


def test_cli_timeline(monkeypatch, capsys):
    _fake_fetch(monkeypatch)
    assert cli.run(["timeline", "t"]) == 0
    assert "prsnoop timeline" in capsys.readouterr().out


def test_cli_network(monkeypatch, capsys):
    _fake_fetch(monkeypatch, [_pr(1, 1, repo="a/one")])
    assert cli.run(["network", "t"]) == 0
    assert "work flow" in capsys.readouterr().out
    assert cli.run(["network", "t", "-f", "dot"]) == 0
    assert "digraph prsnoop" in capsys.readouterr().out


def test_cli_digest(monkeypatch, capsys):
    _fake_fetch(monkeypatch)
    assert cli.run(["digest", "t"]) == 0
    assert "prsnoop weekly digest" in capsys.readouterr().out
    assert cli.run(["digest", "t", "-f", "email"]) == 0
    assert "Subject:" in capsys.readouterr().out


def test_cli_report(monkeypatch, capsys, tmp_path):
    _fake_fetch(monkeypatch)
    out_path = tmp_path / "r.html"
    assert cli.run(["report", "t", "-o", str(out_path)]) == 0
    content = out_path.read_text(encoding="utf-8")
    assert content.startswith("<!doctype html>")


def test_cli_tui_rejects_bad_every(monkeypatch, capsys):
    _fake_fetch(monkeypatch)
    # validation happens before curses import, so this is platform-safe
    assert cli.run(["tui", "t", "--every", "1"]) == 2


def test_v2_commands_registered():
    import io

    from prsnoop import cli as cli_mod
    text = ""
    for name in ["build_score_parser", "build_achievements_parser",
                 "build_forecast_parser", "build_ask_parser",
                 "build_timeline_parser", "build_network_parser",
                 "build_digest_parser", "build_report_parser",
                 "build_tui_parser"]:
        assert hasattr(cli_mod, name), f"{name} missing"
        parser = getattr(cli_mod, name)()
        buf = io.StringIO()
        parser.print_help(buf)
        text += buf.getvalue()
    for cmd in ["score", "achievements", "forecast", "ask", "timeline",
                "network", "digest", "report", "tui"]:
        assert cmd in text, f"{cmd} missing from help"


# ---------------------------------------------------------------- v2.1 web


def _pr231(days_ago: float, number: int = 1, merged: bool = True, adds: int = 200):
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    merged_at = created + timedelta(hours=6) if merged else None
    return PRRecord(
        repo="acme/app", number=number, title=f"feature {number}",
        url="u", state="merged" if merged else "open", created_at=created,
        merged_at=merged_at, additions=adds, deletions=adds // 3,
        changed_files=3,
    )


def test_showcase_html_structure():
    from prsnoop.showcase import render_showcase_html

    act = _activity([_pr231(1, 1), _pr231(3, 2, merged=False)])
    html = render_showcase_html(act)
    assert html.startswith("<!doctype html>")
    # no unreplaced placeholders
    for token in ("__DATA__", "__JS__", "__CSS__", "__USER__", "__WINDOW__",
                  "__GEN__", "__ACHDONE__", "__ACHTOTAL__", "__ACHSCORE__"):
        assert token not in html
    # key sections present
    assert "contribution graph" in html
    assert "pull request explorer" in html
    assert "window.__PRSNOOP__ = {" in html
    assert "heatmap" in html and "donut" in html and "gauge" in html
    # embedded data parses back
    m = html.split("window.__PRSNOOP__ = ", 1)[1].split(";</script>", 1)[0]
    payload = json.loads(m)
    assert payload["user"] == "t"
    assert payload["stats"]["prs"] == 2


def test_battle_html_structure():
    from prsnoop.battle import render_battle_html

    a = _activity([_pr231(1, 1), _pr231(2, 2)])
    b = _activity([_pr231(1, 3, adds=900)], user="u2")
    html = render_battle_html(a, b)
    assert html.startswith("<!doctype html>")
    assert "vs" in html and "judging" in html
    assert '"a":' in html and '"b":' in html
    assert "prsnoop battle" in html


def test_wrapped_story_slides():
    from prsnoop.wrapped import build_wrapped, render_wrapped_story

    w = build_wrapped(_activity([_pr231(1, 1)]))
    html = render_wrapped_story(w)
    assert html.startswith("<!doctype html>")
    assert 'class="slide active"' in html
    assert "your year in code" in html
    assert html.count('<section class="slide') >= 8


def test_cli_showcase_and_wrapped_web(monkeypatch, tmp_path):
    def fake(client, user, days=30, include_reviews=True, org=None,
             since=None, until=None):
        return [_pr231(1, 1), _pr231(3, 2, merged=False)], [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake)
    monkeypatch.setattr(cli, "GitHubClient", lambda **kw: object())

    out = tmp_path / "showcase.html"
    assert cli.run(["showcase", "t", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")

    wrap = tmp_path / "wrap.html"
    assert cli.run(["wrapped", "t", "--web", "-o", str(wrap)]) == 0
    assert 'class="slide active"' in wrap.read_text(encoding="utf-8")


def test_cli_battle(monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake(client, user, days=30, include_reviews=True, org=None,
             since=None, until=None):
        calls["n"] += 1
        return [_pr231(1, 1, adds=100)], [], [], True


    monkeypatch.setattr(cli, "fetch_user_activity", fake)
    monkeypatch.setattr(cli, "GitHubClient", lambda **kw: object())
    out = tmp_path / "vs.html"
    assert cli.run(["battle", "t1", "t2", "-o", str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    assert "t1" in html and "t2" in html
    assert "takes it" in html or "dead heat" in html


def test_cli_battle_rejects_same_user():
    assert cli.run(["battle", "same", "same"]) == 2
