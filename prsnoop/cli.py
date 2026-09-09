"""Command-line interface for prsnoop.

prsnoop simonw                             # terminal table, last 30 days
prsnoop simonw --days 90                   # wider window
prsnoop simonw --trend                     # delta vs previous window
prsnoop simonw --since 2026-06-01          # absolute start date
prsnoop simonw --org aio-libs              # one organization only
prsnoop simonw -f markdown -o report.md    # write a report
prsnoop org psf --days 30                  # organization pulse report
prsnoop compare antfu simonw               # head-to-head, same window
prsnoop team alice bob carol               # team leaderboard
prsnoop wrapped simonw                     # year in review superlatives
prsnoop readme simonw                      # profile README generator
prsnoop card simonw -o card.svg            # shareable SVG stat card
prsnoop radar owner/repo                   # open PR triage by staleness
prsnoop changelog owner/repo --tag v1.2.0  # release notes from merged PRs
prsnoop ci simonw --min-prs 5              # CI quality gates + step summary
prsnoop watch simonw --every 60            # live ANSI terminal dashboard
prsnoop replay snap.json                   # re-render reports offline
prsnoop serve simonw                       # live dashboard on 127.0.0.1
prsnoop export simonw                      # full report pack to a folder
prsnoop auth                               # check token / rate limit
prsnoop snap simonw -o snap.json           # frozen snapshot for tests
prsnoop snap simonw --compare snap.json    # diff two windows
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prsnoop import __version__
from prsnoop.fetch import fetch_user_activity
from prsnoop.github import GitHubClient, GitHubError, RateLimitExceeded
from prsnoop.models import Activity, Stats
from prsnoop.render import RENDERERS
from prsnoop.stats import build_activity, build_trend, sort_prs

log = logging.getLogger("prsnoop")


def _validate_date(value: str, option: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        print(f"prsnoop: {option} must be YYYY-MM-DD (got {value})", file=sys.stderr)
        raise SystemExit(2) from None
    return value


def _previous_window(since: str | None, until: str | None, days: int) -> tuple[str, str]:
    """Date bounds of the window immediately before the current one.

    Relative windows (--days N) shift N days back; absolute windows
    (--since/--until) shift by their own length so both windows are the
    same size and the deltas are honest.
    """
    if since and until:
        start = datetime.strptime(since, "%Y-%m-%d").date()
        end = datetime.strptime(until, "%Y-%m-%d").date()
        length = (end - start).days + 1
        prev_until = start - timedelta(days=1)
        prev_since = prev_until - timedelta(days=length - 1)
        return prev_since.isoformat(), prev_until.isoformat()
    if since:
        start = datetime.strptime(since, "%Y-%m-%d").date()
        prev_until = start - timedelta(days=1)
        prev_since = prev_until - timedelta(days=days - 1)
        return prev_since.isoformat(), prev_until.isoformat()
    today = datetime.now(timezone.utc).date()
    cur_since = today - timedelta(days=days)
    prev_until = cur_since - timedelta(days=1)
    prev_since = cur_since - timedelta(days=days)
    return prev_since.isoformat(), prev_until.isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prsnoop",
        description="Snoop GitHub pull requests, issues, and reviews into clean reports.",
    )
    parser.add_argument("user", nargs="?", help="GitHub username to snoop")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="look-back window in days (default: 30)",
    )
    parser.add_argument(
        "--last",
        choices=["week", "month", "quarter", "year"],
        default=None,
        help="window preset (overrides --days)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="absolute start date YYYY-MM-DD (overrides --days)",
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help="absolute end date YYYY-MM-DD (requires --since)",
    )
    parser.add_argument(
        "--org",
        type=str,
        default=None,
        help="restrict to one organization or owner (e.g. aio-libs)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=sorted(RENDERERS),
        default="table",
        help="output format (default: table)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="write to a file instead of stdout",
    )
    parser.add_argument(
        "--no-reviews",
        action="store_true",
        help="skip scanning for reviews given (fewer API calls)",
    )
    parser.add_argument(
        "--trend",
        action="store_true",
        help="compare this window against the one before it (doubles API calls)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="bypass the local cache for fresh data",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    parser.add_argument(
        "--sort",
        choices=["recent", "oldest", "merge-time", "size", "repo"],
        default="recent",
        help="sort PR listing by key (default: recent)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")

    return parser


def build_snap_parser() -> argparse.ArgumentParser:
    """Parser for the snap subcommand (its own argv after 'snap')."""
    snap_p = argparse.ArgumentParser(
        prog="prsnoop snap",
        description="Save or compare frozen JSON snapshots of a user's activity.",
    )
    snap_p.add_argument("user", help="GitHub username")
    snap_p.add_argument("-o", "--output", type=Path, default=None, help="snapshot path")
    snap_p.add_argument(
        "--compare", type=Path, default=None, help="compare against this snapshot"
    )
    snap_p.add_argument("--days", type=int, default=30)
    snap_p.add_argument("--since", type=str, default=None)
    snap_p.add_argument("--until", type=str, default=None)
    snap_p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    snap_p.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return snap_p


def build_compare_parser() -> argparse.ArgumentParser:
    """Parser for the compare subcommand."""
    cmp_p = argparse.ArgumentParser(
        prog="prsnoop compare",
        description="Side-by-side contribution comparison of two users over one window.",
    )
    cmp_p.add_argument("user_a", help="first GitHub username")
    cmp_p.add_argument("user_b", help="second GitHub username")
    cmp_p.add_argument("--days", type=int, default=30)
    cmp_p.add_argument("--since", type=str, default=None)
    cmp_p.add_argument("--until", type=str, default=None)
    cmp_p.add_argument("--org", type=str, default=None, help="restrict both to one org")
    cmp_p.add_argument(
        "--format",
        "-f",
        choices=["table", "markdown", "csv", "json"],
        default="table",
    )
    cmp_p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    cmp_p.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return cmp_p


def build_org_parser(kind: str = "org") -> argparse.ArgumentParser:
    """Parser for the org and repo pulse subcommands."""
    prog = f"prsnoop {kind}"
    org_p = argparse.ArgumentParser(
        prog=prog,
        description=(
            f"Pulse report for a GitHub {kind}: who ships, what is hot,"
            " how fast merges land."
        ),
    )
    org_p.add_argument(
        kind, help=f"GitHub {kind} login" if kind == "org" else "repository as owner/name"
    )
    org_p.add_argument("--days", type=int, default=30)
    org_p.add_argument(
        "--last",
        choices=["week", "month", "quarter", "year"],
        default=None,
        help="window preset (overrides --days)",
    )
    org_p.add_argument("--since", type=str, default=None)
    org_p.add_argument("--until", type=str, default=None)
    org_p.add_argument(
        "--format",
        "-f",
        choices=["table", "markdown", "html", "csv", "json", "badge"],
        default="table",
    )
    org_p.add_argument("--output", "-o", type=Path, default=None, help="write to a file")
    org_p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    org_p.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return org_p


_LAST_TO_DAYS = {"week": 7, "month": 30, "quarter": 91, "year": 365}


def cmd_org(args: argparse.Namespace) -> int:
    from prsnoop.badge import render_pulse_badge
    from prsnoop.org import fetch_org_pulse, fetch_repo_pulse
    from prsnoop.render import (
        render_org_csv,
        render_org_html,
        render_org_markdown,
        render_org_table,
    )

    kind: str = getattr(args, "kind", "org")
    subject = str(getattr(args, "org", None) or getattr(args, "repo", None) or "")
    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    days = _LAST_TO_DAYS[args.last] if getattr(args, "last", None) else args.days
    if days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    if args.until and not args.since:
        print("prsnoop: --until requires --since", file=sys.stderr)
        return 2
    if kind == "repo" and "/" not in subject:
        print("prsnoop: repo must be owner/name", file=sys.stderr)
        return 2
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    fetcher = fetch_repo_pulse if kind == "repo" else fetch_org_pulse
    try:
        prs, pulse = fetcher(client, subject, days=days, since=since, until=until)
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        print(
            "prsnoop: set PRSNOOP_TOKEN or GITHUB_TOKEN to raise the limit",
            file=sys.stderr,
        )
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3

    if args.format == "json":
        rendered = json.dumps(pulse.to_dict(), indent=2)
    elif args.format == "markdown":
        rendered = render_org_markdown(prs, pulse)
    elif args.format == "html":
        rendered = render_org_html(prs, pulse)
    elif args.format == "csv":
        rendered = render_org_csv(prs, pulse)
    elif args.format == "badge":
        rendered = render_pulse_badge(pulse)
    else:
        rendered = render_org_table(prs, pulse)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"prsnoop: wrote {args.output}", file=sys.stderr)
    else:
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                with contextlib.suppress(ValueError, OSError):
                    reconfigure(encoding="utf-8")
        print(rendered)
    return 0


def build_serve_parser() -> argparse.ArgumentParser:
    """Parser for the serve subcommand."""
    s = argparse.ArgumentParser(
        prog="prsnoop serve",
        description=(
            "Live local dashboard: fresh HTML report on 127.0.0.1,"
            " auto-refreshing, JSON at /api/report."
        ),
    )
    s.add_argument(
        "targets",
        nargs="+",
        help="one or more of: username, org:login, repo:owner/name",
    )
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--last", choices=["week", "month", "quarter", "year"], default=None)
    s.add_argument("--port", type=int, default=8642)
    s.add_argument("--open", action="store_true", help="open the browser")
    s.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    s.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return s


def build_team_parser() -> argparse.ArgumentParser:
    """Parser for the team subcommand."""
    tm = argparse.ArgumentParser(
        prog="prsnoop team",
        description="Leaderboard across two or more contributors, one window.",
    )
    tm.add_argument("users", nargs="+", help="two or more GitHub usernames")
    tm.add_argument("--days", type=int, default=30)
    tm.add_argument("--last", choices=["week", "month", "quarter", "year"], default=None)
    tm.add_argument("--since", type=str, default=None)
    tm.add_argument("--until", type=str, default=None)
    tm.add_argument(
        "--format", "-f", choices=["table", "markdown", "csv", "json"], default="table"
    )
    tm.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    tm.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return tm


def build_export_parser() -> argparse.ArgumentParser:
    """Parser for the export subcommand."""
    ex = argparse.ArgumentParser(
        prog="prsnoop export",
        description=(
            "Write the full report pack (txt, md, html, csv, json, badges)"
            " into a folder with one command."
        ),
    )
    ex.add_argument("user", help="GitHub username")
    ex.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output folder (default: prsnoop-USER-DATE)",
    )
    ex.add_argument("--days", type=int, default=30)
    ex.add_argument("--last", choices=["week", "month", "quarter", "year"], default=None)
    ex.add_argument("--since", type=str, default=None)
    ex.add_argument("--until", type=str, default=None)
    ex.add_argument("--org", type=str, default=None, help="restrict to one org")
    ex.add_argument("--trend", action="store_true")
    ex.add_argument("--no-reviews", action="store_true")
    ex.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    ex.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return ex


def build_wrapped_parser() -> argparse.ArgumentParser:
    """Parser for the wrapped subcommand."""
    w = argparse.ArgumentParser(
        prog="prsnoop wrapped",
        description=(
            "Year in review: the superlatives behind one contributor's"
            " pull requests. Biggest patch, busiest month, longest streak."
        ),
    )
    w.add_argument("user", help="GitHub username")
    w.add_argument("--days", type=int, default=365)
    w.add_argument("--since", type=str, default=None)
    w.add_argument("--until", type=str, default=None)
    w.add_argument("--format", "-f", choices=["table", "markdown", "json"], default="table")
    w.add_argument("--output", "-o", type=Path, default=None, help="write to a file")
    w.add_argument("--no-reviews", action="store_true")
    w.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    w.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return w


def build_readme_parser() -> argparse.ArgumentParser:
    """Parser for the readme subcommand."""
    r = argparse.ArgumentParser(
        prog="prsnoop readme",
        description=(
            "Generate a paste-ready GitHub profile README section:"
            " badges, stats table, top repositories."
        ),
    )
    r.add_argument("user", help="GitHub username")
    r.add_argument("--days", type=int, default=30)
    r.add_argument("--last", choices=["week", "month", "quarter", "year"], default=None)
    r.add_argument("--since", type=str, default=None)
    r.add_argument("--until", type=str, default=None)
    r.add_argument("--org", type=str, default=None, help="restrict to one org")
    r.add_argument("--trend", action="store_true")
    r.add_argument("--no-reviews", action="store_true")
    r.add_argument("--output", "-o", type=Path, default=None, help="write to a file")
    r.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    r.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return r


def build_card_parser() -> argparse.ArgumentParser:
    """Parser for the card subcommand."""
    c = argparse.ArgumentParser(
        prog="prsnoop card",
        description=(
            "Shareable SVG stat card: a contributor scoreboard to drop"
            " into a profile README or pin, no hosting service needed."
        ),
    )
    c.add_argument("user", help="GitHub username")
    c.add_argument("--days", type=int, default=30)
    c.add_argument("--last", choices=["week", "month", "quarter", "year"], default=None)
    c.add_argument("--since", type=str, default=None)
    c.add_argument("--until", type=str, default=None)
    c.add_argument("--org", type=str, default=None)
    c.add_argument(
        "--theme",
        choices=["dark", "light"],
        default="dark",
        help="card palette (default: dark)",
    )
    c.add_argument("--no-reviews", action="store_true")
    c.add_argument("--output", "-o", type=Path, default=None)
    c.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    c.add_argument("--verbose", "-v", action="store_true")
    return c


def build_radar_parser() -> argparse.ArgumentParser:
    """Parser for the radar subcommand."""
    r = argparse.ArgumentParser(
        prog="prsnoop radar",
        description=(
            "Maintainer triage radar: every open pull request on a"
            " repository, ranked by waiting age with staleness buckets."
        ),
    )
    r.add_argument("repo", help="repository as owner/name")
    r.add_argument(
        "--limit",
        type=int,
        default=300,
        help="cap the scan at this many open PRs (default: 300)",
    )
    r.add_argument(
        "--format",
        "-f",
        choices=["table", "markdown", "json", "csv"],
        default="table",
    )
    r.add_argument("--output", "-o", type=Path, default=None)
    r.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    r.add_argument("--verbose", "-v", action="store_true")
    return r


def build_changelog_parser() -> argparse.ArgumentParser:
    """Parser for the changelog subcommand."""
    g = argparse.ArgumentParser(
        prog="prsnoop changelog",
        description=(
            "Release notes from merged pull requests: grouped by type,"
            " paste-ready for a release page or CHANGELOG."
        ),
    )
    g.add_argument("repo", help="repository as owner/name")
    g.add_argument("--days", type=int, default=30)
    g.add_argument("--since", type=str, default=None)
    g.add_argument("--until", type=str, default=None)
    g.add_argument(
        "--tag",
        type=str,
        default=None,
        help="collect PRs merged since this tag (e.g. v1.2.0)",
    )
    g.add_argument(
        "--limit",
        type=int,
        default=200,
        help="cap the entry list at this many PRs (default: 200)",
    )
    g.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown")
    g.add_argument("--output", "-o", type=Path, default=None)
    g.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    g.add_argument("--verbose", "-v", action="store_true")
    return g


def build_ci_parser() -> argparse.ArgumentParser:
    """Parser for the ci subcommand."""
    c = argparse.ArgumentParser(
        prog="prsnoop ci",
        description=(
            "Contribution quality gates for CI: fetch the window, apply"
            " thresholds, write the GitHub step summary, and exit nonzero"
            " when a gate fails."
        ),
    )
    c.add_argument("user", help="GitHub username to gate")
    c.add_argument("--days", type=int, default=30)
    c.add_argument("--last", choices=["week", "month", "quarter", "year"], default=None)
    c.add_argument("--since", type=str, default=None)
    c.add_argument("--until", type=str, default=None)
    c.add_argument("--org", type=str, default=None)
    c.add_argument("--no-reviews", action="store_true")
    c.add_argument(
        "--min-prs",
        type=int,
        default=None,
        help="gate: at least this many PRs opened",
    )
    c.add_argument(
        "--min-merged",
        type=int,
        default=None,
        help="gate: at least this many PRs merged",
    )
    c.add_argument(
        "--min-reviews",
        type=int,
        default=None,
        help="gate: at least this many reviews given",
    )
    c.add_argument(
        "--min-merge-rate",
        type=float,
        default=None,
        help="gate: merge rate at or above this percent",
    )
    c.add_argument(
        "--max-merge-days",
        type=float,
        default=None,
        help="gate: median days to merge at or below this",
    )
    c.add_argument("--output", "-o", type=Path, default=None)
    c.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    c.add_argument("--verbose", "-v", action="store_true")
    return c


def build_watch_parser() -> argparse.ArgumentParser:
    """Parser for the watch subcommand."""
    w = argparse.ArgumentParser(
        prog="prsnoop watch",
        description=(
            "Live ANSI dashboard in the terminal: refetches every N"
            " seconds, redraws, and flags new pull requests as they land."
        ),
    )
    w.add_argument("user", help="GitHub username")
    w.add_argument("--days", type=int, default=30)
    w.add_argument("--since", type=str, default=None)
    w.add_argument("--until", type=str, default=None)
    w.add_argument("--org", type=str, default=None)
    w.add_argument(
        "--every",
        type=int,
        default=60,
        help="seconds between refreshes (default: 60)",
    )
    w.add_argument(
        "--once",
        action="store_true",
        help="render one frame and exit (also handy for demos)",
    )
    w.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    w.add_argument("--no-reviews", action="store_true")
    w.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    w.add_argument("--verbose", "-v", action="store_true")
    return w


def build_replay_parser() -> argparse.ArgumentParser:
    """Parser for the replay subcommand."""
    p = argparse.ArgumentParser(
        prog="prsnoop replay",
        description=(
            "Re-render any report from a saved snapshot JSON with no"
            " network: reproducible reports for tests and CI."
        ),
    )
    p.add_argument("snapshot", type=Path, help="snapshot file from prsnoop snap")
    p.add_argument("--format", "-f", choices=sorted(RENDERERS), default="table")
    p.add_argument(
        "--wrapped",
        action="store_true",
        help="render the wrapped superlatives instead of the report",
    )
    p.add_argument("--output", "-o", type=Path, default=None)
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def cmd_auth(args: argparse.Namespace) -> int:
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    try:
        rate = client.get("/rate_limit")
    except GitHubError as exc:
        print(f"prsnoop auth: {exc}", file=sys.stderr)
        return 3
    if args.clear_cache and args.cache_dir.exists():
        for f in args.cache_dir.glob("*.json"):
            f.unlink()
        print("cache cleared")
    if not isinstance(rate, dict):
        print("prsnoop auth: unexpected rate limit response", file=sys.stderr)
        return 3
    core = rate.get("resources", {}).get("core", {})
    search = rate.get("resources", {}).get("search", {})
    if client.token:
        tok = "token detected"
    else:
        tok = "no token (anonymous: 60 req/hr, search hidden)"
    print(f"auth: {tok}")
    print(f"core:   {core.get('remaining', '?')}/{core.get('limit', '?')} remaining")
    print(f"search: {search.get('remaining', '?')}/{search.get('limit', '?')} remaining")
    print(f"cache:  {args.cache_dir}")
    if not client.token:
        print("set PRSNOOP_TOKEN or GITHUB_TOKEN for 5000 req/hr and full search access")
    return 0


def cmd_snap(args: argparse.Namespace) -> int:
    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    try:
        prs, reviews, issues, _ = fetch_user_activity(
            client,
            args.user,
            days=args.days,
            include_reviews=True,
            since=since,
            until=until,
        )
    except (GitHubError, RateLimitExceeded) as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3
    activity = build_activity(
        args.user,
        prs,
        reviews,
        issues,
        window_days=args.days,
        since=since or "",
        until=until or "",
    )
    if args.compare:
        return _compare_snapshots(args.compare, activity)
    if not args.output:
        print("prsnoop: snap requires -o SNAPSHOT or --compare SNAPSHOT", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(activity.to_dict(), indent=2), encoding="utf-8")
    print(f"prsnoop: wrote {args.output}", file=sys.stderr)
    return 0


def _compare_snapshots(old_path: Path, new: Activity) -> int:
    try:
        old = json.loads(old_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"prsnoop: cannot read snapshot: {exc}", file=sys.stderr)
        return 2
    old_stats, new_stats = old["stats"], new.stats.to_dict()
    deltas = [
        ("pull requests", "prs_authored"),
        ("merged", "prs_merged"),
        ("reviews given", "reviews_given"),
        ("issues opened", "issues_opened"),
        ("lines added", "lines_added"),
        ("lines deleted", "lines_deleted"),
    ]
    print(f"prsnoop | {new.user} | change since {old_stats.get('generated_at', '?')}")
    for label, key in deltas:
        a, b = old_stats.get(key, 0), new_stats.get(key, 0)
        sign = "+" if b >= a else "-"
        print(f"  {label:14} {a} -> {b}  ({sign}{abs(b - a)})")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    users = [args.user_a, args.user_b]
    activities: list[Activity] = []
    for user in users:
        try:
            prs, reviews, issues, _ = fetch_user_activity(
                client,
                user,
                days=args.days,
                include_reviews=False,
                org=args.org,
                since=since,
                until=until,
            )
        except (GitHubError, RateLimitExceeded) as exc:
            print(f"prsnoop: {exc}", file=sys.stderr)
            return 3
        activities.append(
            build_activity(
                user,
                prs,
                reviews,
                issues,
                window_days=args.days,
                since=since or "",
                until=until or "",
            )
        )

    a, b = activities[0].stats, activities[1].stats
    rows = [
        ("pull requests", a.prs_authored, b.prs_authored, "high"),
        ("merged", a.prs_merged, b.prs_merged, "high"),
        ("merge rate", f"{a.merge_rate * 100:.0f}%", f"{b.merge_rate * 100:.0f}%", "high"),
        ("issues opened", a.issues_opened, b.issues_opened, "high"),
        (
            "median merge",
            _fmt_days_str(a.median_days_to_merge),
            _fmt_days_str(b.median_days_to_merge),
            "low",
        ),
        (
            "longest streak",
            f"{a.longest_streak_days}d",
            f"{b.longest_streak_days}d",
            "high",
        ),
        ("repos", a.distinct_repos, b.distinct_repos, "high"),
    ]

    def esc(v: object) -> str:
        return str(v).replace("|", "\\|")

    if args.format == "json":
        payload = {
            "users": [args.user_a, args.user_b],
            "metrics": [
                {
                    "metric": label,
                    args.user_a: av if isinstance(av, int) else str(av),
                    args.user_b: bv if isinstance(bv, int) else str(bv),
                }
                for label, av, bv, _better in rows
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0
    if args.format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["metric", args.user_a, args.user_b])
        for label, av, bv, _better in rows:
            writer.writerow([label, av, bv])
        print(buf.getvalue(), end="")
        return 0
    if args.format == "markdown":
        lines = [
            f"# {args.user_a} vs {args.user_b}",
            "",
            "_Same window for both, generated by [prsnoop]"
            "(https://github.com/MohammedAnasNathani/prsnoop)_",
            "",
            "| Metric | " + f"{args.user_a} | {args.user_b} |",
            "|---|---:|---:|",
        ]
        for label, av, bv, _better in rows:
            lines.append(f"| {esc(label)} | {esc(av)} | {esc(bv)} |")
        print("\n".join(lines))
    else:
        label_w = 18
        name_a, name_b = args.user_a[:14], args.user_b[:14]
        print(f"prsnoop | {args.user_a} vs {args.user_b}")
        print("window: same for both")
        print()
        print(f"  {'metric':<{label_w}} {name_a:>14}  {name_b:>14}")
        print(f"  {'-' * label_w} {'-' * 14}  {'-' * 14}")
        for label, av, bv, _better in rows:
            print(f"  {label:<{label_w}} {str(av):>14}  {str(bv):>14}")
    return 0


def _fmt_days_str(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}d"


def cmd_serve(args: argparse.Namespace) -> int:
    from prsnoop.serve import serve

    days = _LAST_TO_DAYS[args.last] if args.last else args.days
    if days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    print(
        f"prsnoop: serving {', '.join(args.targets)} (last {days} days) at"
        f" http://127.0.0.1:{args.port}/  (ctrl-c to stop)",
        file=sys.stderr,
    )
    serve(
        args.targets,
        days=days,
        port=args.port,
        cache_dir=args.cache_dir,
        open_browser=args.open,
    )
    print("prsnoop: dashboard stopped", file=sys.stderr)
    return 0


# Team mode skips review scans for speed, so no reviews column here.
_TEAM_COLUMNS = (
    ("prs", lambda s: s.prs_authored),
    ("merged", lambda s: s.prs_merged),
    ("rate", lambda s: f"{s.merge_rate * 100:.0f}%"),
    ("issues", lambda s: s.issues_opened),
    ("median", lambda s: _fmt_days_str(s.median_days_to_merge)),
    ("streak", lambda s: f"{s.longest_streak_days}d"),
    ("repos", lambda s: s.distinct_repos),
)


def cmd_team(args: argparse.Namespace) -> int:
    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    days = _LAST_TO_DAYS[args.last] if args.last else args.days
    if len(args.users) < 2:
        print("prsnoop: team needs two or more usernames", file=sys.stderr)
        return 2
    if len(set(args.users)) != len(args.users):
        print("prsnoop: team has duplicate usernames", file=sys.stderr)
        return 2
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    stats: list[Stats] = []
    for user in args.users:
        try:
            prs, reviews, issues, _ = fetch_user_activity(
                client,
                user,
                days=days,
                include_reviews=False,
                since=since,
                until=until,
            )
        except RateLimitExceeded as exc:
            print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
            return 4
        except GitHubError as exc:
            print(f"prsnoop: {exc}", file=sys.stderr)
            return 3
        stats.append(
            build_activity(
                user,
                prs,
                reviews,
                issues,
                window_days=days,
                since=since or "",
                until=until or "",
            ).stats
        )
    stats.sort(key=lambda s: (-s.prs_merged, -s.prs_authored))

    if args.format == "json":
        payload = {
            "window_days": days,
            "since": since or "",
            "until": until or "",
            "ranking": [
                {
                    "rank": i + 1,
                    "user": s.user,
                    **{name: fn(s) for name, fn in _TEAM_COLUMNS},
                }
                for i, s in enumerate(stats)
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0
    if args.format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["rank", "user", *[name for name, _ in _TEAM_COLUMNS]])
        for i, s in enumerate(stats):
            writer.writerow([i + 1, s.user, *[fn(s) for _, fn in _TEAM_COLUMNS]])
        print(buf.getvalue(), end="")
        return 0

    def esc(v: object) -> str:
        return str(v).replace("|", "\\|")

    headers = [name for name, _ in _TEAM_COLUMNS]
    if args.format == "markdown":
        lines = [
            "# Team leaderboard",
            "",
            f"_Window: last {days} days, ranked by merged PRs."
            " Generated by [prsnoop](https://github.com/MohammedAnasNathani/prsnoop)_",
            "",
            "| # | User | " + " | ".join(headers) + " |",
            "|---|---|" + "|".join("---:" for _ in headers) + "|",
        ]
        for i, s in enumerate(stats):
            row = " | ".join(esc(fn(s)) for _, fn in _TEAM_COLUMNS)
            lines.append(f"| {i + 1} | **{esc(s.user)}** | {row} |")
        print("\n".join(lines))
        return 0

    name_w = max(14, max(len(s.user) for s in stats))
    print("prsnoop team | ranked by merged")
    print(f"window: last {days} days")
    print()
    print(f"  {'#':>2}  {'user':<{name_w}}  " + "  ".join(f"{h:>8}" for h in headers))
    print(f"  {'--':>2}  {'-' * name_w}  " + "  ".join("-" * 8 for _ in headers))
    for i, s in enumerate(stats):
        row = "  ".join(f"{str(fn(s)):>8}" for _, fn in _TEAM_COLUMNS)
        lead = " *" if i == 0 and stats[0].prs_merged > 0 else ""
        print(f"  {i + 1:>2}  {s.user:<{name_w}}  {row}{lead}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from prsnoop.badge import render_badge

    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    days = _LAST_TO_DAYS[args.last] if args.last else args.days
    if days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    if args.until and not args.since:
        print("prsnoop: --until requires --since", file=sys.stderr)
        return 2
    out_dir = args.output or Path(
        f"prsnoop-{args.user}-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    )
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    try:
        prs, reviews, issues, fully = fetch_user_activity(
            client,
            args.user,
            days=days,
            include_reviews=not args.no_reviews,
            org=args.org,
            since=since,
            until=until,
        )
        activity = build_activity(
            args.user,
            prs,
            reviews,
            issues,
            window_days=days,
            since=since or "",
            until=until or "",
        )
        if args.trend:
            prev_since, prev_until = _previous_window(since, until, days)
            try:
                p_prs, p_rev, p_iss, _ = fetch_user_activity(
                    client,
                    args.user,
                    days=days,
                    include_reviews=not args.no_reviews,
                    org=args.org,
                    since=prev_since,
                    until=prev_until,
                )
                prev_activity = build_activity(
                    args.user,
                    p_prs,
                    p_rev,
                    p_iss,
                    window_days=days,
                    since=prev_since,
                    until=prev_until,
                )
                activity.trend = build_trend(activity.stats, prev_activity.stats)
            except (GitHubError, RateLimitExceeded) as exc:
                print(f"prsnoop: trend window skipped: {exc}", file=sys.stderr)
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3

    out_dir.mkdir(parents=True, exist_ok=True)
    pack = {
        "report.txt": RENDERERS["table"](activity),
        "report.md": RENDERERS["markdown"](activity),
        "report.html": RENDERERS["html"](activity),
        "report.csv": RENDERERS["csv"](activity),
        "report.json": RENDERERS["json"](activity),
        "badges.md": render_badge(activity),
    }
    for name, content in pack.items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        print(f"prsnoop: wrote {path}", file=sys.stderr)
    if not fully:
        print(
            "prsnoop: note: large result set, lines-changed totals are partial",
            file=sys.stderr,
        )
    print(f"prsnoop: export complete in {out_dir}", file=sys.stderr)
    return 0


def _fetch_activity(args: argparse.Namespace, days: int) -> Activity:
    """Shared fetch for wrapped and readme (raises GitHubError upward)."""
    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    if args.until and not args.since:
        print("prsnoop: --until requires --since", file=sys.stderr)
        raise SystemExit(2)
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    prs, reviews, issues, _ = fetch_user_activity(
        client,
        args.user,
        days=days,
        include_reviews=not args.no_reviews,
        org=getattr(args, "org", None),
        since=since,
        until=until,
    )
    activity = build_activity(
        args.user,
        prs,
        reviews,
        issues,
        window_days=days,
        since=since or "",
        until=until or "",
    )
    if getattr(args, "trend", False):
        prev_since, prev_until = _previous_window(since, until, days)
        try:
            p_prs, p_rev, p_iss, _ = fetch_user_activity(
                client,
                args.user,
                days=days,
                include_reviews=not args.no_reviews,
                org=getattr(args, "org", None),
                since=prev_since,
                until=prev_until,
            )
            prev_activity = build_activity(
                args.user,
                p_prs,
                p_rev,
                p_iss,
                window_days=days,
                since=prev_since,
                until=prev_until,
            )
            activity.trend = build_trend(activity.stats, prev_activity.stats)
        except (GitHubError, RateLimitExceeded) as exc:
            print(f"prsnoop: trend window skipped: {exc}", file=sys.stderr)
    return activity


def _emit(rendered: str, output: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"prsnoop: wrote {output}", file=sys.stderr)
    else:
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                with contextlib.suppress(ValueError, OSError):
                    reconfigure(encoding="utf-8")
        print(rendered)


def cmd_wrapped(args: argparse.Namespace) -> int:
    from prsnoop.wrapped import build_wrapped, render_wrapped_markdown, render_wrapped_table

    days = args.days
    if days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    try:
        activity = _fetch_activity(args, days)
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3
    wrapped = build_wrapped(activity)
    if args.format == "json":
        rendered = json.dumps(wrapped.to_dict(), indent=2)
    elif args.format == "markdown":
        rendered = render_wrapped_markdown(wrapped)
    else:
        rendered = render_wrapped_table(wrapped)
    _emit(rendered, args.output)
    return 0


def cmd_readme(args: argparse.Namespace) -> int:
    from prsnoop.render import render_profile_readme

    days = _LAST_TO_DAYS[args.last] if args.last else args.days
    if days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    try:
        activity = _fetch_activity(args, days)
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3
    _emit(render_profile_readme(activity), args.output)
    return 0


def cmd_card(args: argparse.Namespace) -> int:
    from prsnoop.card import render_card

    days = _LAST_TO_DAYS[args.last] if args.last else args.days
    if days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    try:
        activity = _fetch_activity(args, days)
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3
    _emit(render_card(activity, theme=args.theme), args.output)
    return 0


def cmd_radar(args: argparse.Namespace) -> int:
    from prsnoop.radar import (
        fetch_radar,
        render_radar_csv,
        render_radar_markdown,
        render_radar_table,
    )

    if "/" not in args.repo:
        print("prsnoop: radar needs a repository as owner/name", file=sys.stderr)
        return 2
    if args.limit < 1:
        print("prsnoop: --limit must be >= 1", file=sys.stderr)
        return 2
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    try:
        report = fetch_radar(client, args.repo, limit=args.limit)
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3
    if args.format == "json":
        rendered = json.dumps(report.to_dict(), indent=2)
    elif args.format == "markdown":
        rendered = render_radar_markdown(report)
    elif args.format == "csv":
        rendered = render_radar_csv(report)
    else:
        rendered = render_radar_table(report)
    _emit(rendered, args.output)
    return 0


def cmd_changelog(args: argparse.Namespace) -> int:
    from prsnoop.changelog import (
        build_changelog,
        render_changelog_json,
        render_changelog_markdown,
    )

    if "/" not in args.repo:
        print(
            "prsnoop: changelog needs a repository as owner/name",
            file=sys.stderr,
        )
        return 2
    if args.days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    if args.until and not args.since:
        print("prsnoop: --until requires --since", file=sys.stderr)
        return 2
    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    try:
        ch = build_changelog(
            client,
            args.repo,
            days=args.days,
            since=since,
            until=until,
            tag=args.tag,
            limit=args.limit,
        )
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3
    rendered = (
        render_changelog_json(ch)
        if args.format == "json"
        else render_changelog_markdown(ch)
    )
    _emit(rendered, args.output)
    return 0


def cmd_ci(args: argparse.Namespace) -> int:
    import os

    from prsnoop.ci import check_gates, render_summary

    days = _LAST_TO_DAYS[args.last] if args.last else args.days
    if days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    gates_spec = {
        "min_prs": args.min_prs,
        "min_merged": args.min_merged,
        "min_reviews": args.min_reviews,
        "min_merge_rate": args.min_merge_rate,
        "max_merge_days": args.max_merge_days,
    }
    try:
        activity = _fetch_activity(args, days)
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3
    gates = check_gates(activity.stats, **gates_spec)
    summary = render_summary(activity, gates)
    step_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_path:
        try:
            with open(step_path, "a", encoding="utf-8") as fh:
                fh.write(summary)
            print("prsnoop: step summary written", file=sys.stderr)
        except OSError as exc:
            print(f"prsnoop: cannot write step summary: {exc}", file=sys.stderr)
    _emit(summary, args.output)
    failed = [g for g in gates if not g.passed]
    if failed:
        print(
            f"prsnoop ci: {len(failed)} of {len(gates)} gates failed",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    import time

    from prsnoop.ansi import supports_color
    from prsnoop.watch import BELL, diff_keys, pr_keys, render_frame

    if args.days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    if args.every < 1:
        print("prsnoop: --every must be >= 1", file=sys.stderr)
        return 2
    if args.until and not args.since:
        print("prsnoop: --until requires --since", file=sys.stderr)
        return 2
    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    if args.color == "always":
        color = True
    elif args.color == "never":
        color = False
    else:
        color = supports_color(sys.stdout)
    client = GitHubClient(cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}")
    previous: set[str] | None = None
    tick = 0
    while True:
        try:
            prs, reviews, issues, _ = fetch_user_activity(
                client,
                args.user,
                days=args.days,
                include_reviews=not args.no_reviews,
                org=args.org,
                since=since,
                until=until,
            )
            activity = build_activity(
                args.user,
                prs,
                reviews,
                issues,
                window_days=args.days,
                since=since or "",
                until=until or "",
            )
            current = pr_keys(activity)
            new_keys, _gone = diff_keys(previous, current)
            frame = render_frame(activity, color=color, new_keys=new_keys, tick=tick + 1)
            for stream in (sys.stdout, sys.stderr):
                reconfigure = getattr(stream, "reconfigure", None)
                if reconfigure is not None:
                    with contextlib.suppress(ValueError, OSError):
                        reconfigure(encoding="utf-8")
            print(frame)
            if new_keys and previous is not None:
                sys.stdout.write(BELL)
            previous = current
            tick += 1
            if args.once:
                return 0
            time.sleep(args.every)
        except KeyboardInterrupt:
            print("\nprsnoop: watch stopped")
            return 0
        except (GitHubError, RateLimitExceeded) as exc:
            print(
                f"prsnoop watch: refresh failed: {exc}; retrying in {args.every}s",
                file=sys.stderr,
            )
            if args.once:
                return 3
            try:
                time.sleep(args.every)
            except KeyboardInterrupt:
                print("\nprsnoop: watch stopped")
                return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from prsnoop.models import Activity
    from prsnoop.wrapped import (
        build_wrapped,
        render_wrapped_markdown,
        render_wrapped_table,
    )

    try:
        data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"prsnoop: cannot read snapshot: {exc}", file=sys.stderr)
        return 2
    try:
        activity = Activity.from_dict(data)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        print(f"prsnoop: not a valid prsnoop snapshot: {exc}", file=sys.stderr)
        return 2
    if args.wrapped:
        wrapped = build_wrapped(activity)
        rendered = (
            render_wrapped_markdown(wrapped)
            if args.format == "markdown"
            else render_wrapped_table(wrapped)
        )
    else:
        rendered = RENDERERS[args.format](activity)
    _emit(rendered, args.output)
    return 0


def run(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "auth":
        auth_parser = argparse.ArgumentParser(
            prog="prsnoop auth",
            description="Check token and rate limit status.",
        )
        auth_parser.add_argument(
            "--clear-cache", action="store_true", help="empty the cache dir"
        )
        auth_parser.add_argument(
            "--cache-dir",
            type=Path,
            default=Path.home() / ".cache" / "prsnoop",
            help="cache directory (default: ~/.cache/prsnoop)",
        )
        auth_parser.add_argument("--verbose", "-v", action="store_true")
        auth_args = auth_parser.parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if auth_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_auth(auth_args)
    if raw and raw[0] == "snap":
        snap_args = build_snap_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if snap_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_snap(snap_args)
    if raw and raw[0] == "compare":
        cmp_args = build_compare_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if cmp_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_compare(cmp_args)
    if raw and raw[0] in ("org", "repo"):
        kind = raw[0]
        org_args = build_org_parser(kind).parse_args(raw[1:])
        org_args.kind = kind
        logging.basicConfig(
            level=logging.DEBUG if org_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_org(org_args)
    if raw and raw[0] == "wrapped":
        w_args = build_wrapped_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if w_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_wrapped(w_args)
    if raw and raw[0] == "readme":
        r_args = build_readme_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if r_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_readme(r_args)
    if raw and raw[0] == "serve":
        serve_args = build_serve_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if serve_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_serve(serve_args)
    if raw and raw[0] == "team":
        team_args = build_team_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if team_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_team(team_args)
    if raw and raw[0] == "export":
        export_args = build_export_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if export_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_export(export_args)
    if raw and raw[0] == "card":
        card_args = build_card_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if card_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_card(card_args)
    if raw and raw[0] == "radar":
        radar_args = build_radar_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if radar_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_radar(radar_args)
    if raw and raw[0] == "changelog":
        changelog_args = build_changelog_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if changelog_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_changelog(changelog_args)
    if raw and raw[0] == "ci":
        ci_args = build_ci_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if ci_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_ci(ci_args)
    if raw and raw[0] == "watch":
        watch_args = build_watch_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if watch_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_watch(watch_args)
    if raw and raw[0] == "replay":
        replay_args = build_replay_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if replay_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_replay(replay_args)
    if raw and raw[0] == "me":
        me_args = build_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if me_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        client = GitHubClient(
            cache_dir=me_args.cache_dir, user_agent=f"prsnoop/{__version__}"
        )
        try:
            who = client.get("/user")
        except (GitHubError, RateLimitExceeded) as exc:
            print(f"prsnoop me: {exc}", file=sys.stderr)
            print(
                "prsnoop me: this subcommand reads your own login from the"
                " API, so it needs PRSNOOP_TOKEN or GITHUB_TOKEN",
                file=sys.stderr,
            )
            return 3
        if not isinstance(who, dict) or "login" not in who:
            print("prsnoop me: unexpected /user response", file=sys.stderr)
            return 3
        return run([who["login"], *raw[1:]])

    args = build_parser().parse_args(raw)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not args.user:
        build_parser().print_help(sys.stderr)
        return 2
    if args.days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    if args.until and not args.since:
        print("prsnoop: --until requires --since", file=sys.stderr)
        return 2
    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    days = _LAST_TO_DAYS[args.last] if args.last else args.days

    try:
        client = GitHubClient(
            cache_dir=args.cache_dir,
            user_agent=f"prsnoop/{__version__}",
        )
        prs, reviews, issues, fully_enriched = fetch_user_activity(
            client,
            args.user,
            days=days,
            include_reviews=not args.no_reviews,
            org=args.org,
            since=since,
            until=until,
        )
        activity = build_activity(
            args.user,
            prs,
            reviews,
            issues,
            window_days=days,
            since=since or "",
            until=until or "",
        )
        # Apply listing sort (does not affect stats)
        activity.prs = sort_prs(activity.prs, args.sort)
        if args.trend:
            prev_since, prev_until = _previous_window(since, until, days)
            try:
                p_prs, p_reviews, p_issues, _ = fetch_user_activity(
                    client,
                    args.user,
                    days=args.days,
                    include_reviews=not args.no_reviews,
                    org=args.org,
                    since=prev_since,
                    until=prev_until,
                )
                prev_activity = build_activity(
                    args.user,
                    p_prs,
                    p_reviews,
                    p_issues,
                    window_days=args.days,
                    since=prev_since,
                    until=prev_until,
                )
                trend = build_trend(activity.stats, prev_activity.stats)
                activity.trend = trend
            except (GitHubError, RateLimitExceeded) as exc:
                print(f"prsnoop: trend window skipped: {exc}", file=sys.stderr)
    except RateLimitExceeded as exc:
        print(f"prsnoop: rate limit hit: {exc}", file=sys.stderr)
        print(
            "prsnoop: set PRSNOOP_TOKEN or GITHUB_TOKEN to raise the limit",
            file=sys.stderr,
        )
        return 4
    except GitHubError as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3

    if not fully_enriched:
        print(
            "prsnoop: note: large result set, lines-changed totals are partial",
            file=sys.stderr,
        )

    rendered = RENDERERS[args.format](activity)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"prsnoop: wrote {args.output}", file=sys.stderr)
    else:
        # Windows consoles default to a legacy code page that cannot encode
        # some report characters; reconfigure for UTF-8 when possible.
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                with contextlib.suppress(ValueError, OSError):
                    reconfigure(encoding="utf-8")
        print(rendered)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
