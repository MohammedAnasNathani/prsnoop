"""Command-line interface for prsnoop.

    prsnoop simonw                             # terminal table, last 30 days
    prsnoop simonw --days 90                   # wider window
    prsnoop simonw --trend                     # delta vs previous window
    prsnoop simonw --since 2026-06-01          # absolute start date
    prsnoop simonw --org aio-libs              # one organization only
    prsnoop simonw -f markdown -o report.md    # write a report
    prsnoop org psf --days 30                  # organization pulse report
    prsnoop compare antfu simonw               # head-to-head, same window
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
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prsnoop import __version__
from prsnoop.fetch import fetch_user_activity
from prsnoop.github import GitHubClient, GitHubError, RateLimitExceeded
from prsnoop.models import CLOSED, MERGED, OPEN, Activity
from prsnoop.render import RENDERERS
from prsnoop.stats import build_activity, build_trend

log = logging.getLogger("prsnoop")


def _validate_date(value: str, option: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        print(
            f"prsnoop: {option} must be YYYY-MM-DD (got {value})", file=sys.stderr
        )
        raise SystemExit(2) from None
    return value


def _previous_window(
    since: str | None, until: str | None, days: int
) -> tuple[str, str]:
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
        "--days", type=int, default=30,
        help="look-back window in days (default: 30)",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="absolute start date YYYY-MM-DD (overrides --days)",
    )
    parser.add_argument(
        "--until", type=str, default=None,
        help="absolute end date YYYY-MM-DD (requires --since)",
    )
    parser.add_argument(
        "--org", type=str, default=None,
        help="restrict to one organization or owner (e.g. aio-libs)",
    )
    parser.add_argument(
        "--format", "-f", choices=sorted(RENDERERS), default="table",
        help="output format (default: table)",
    )
    parser.add_argument(
        "--only", choices=[MERGED, OPEN, CLOSED], default=None,
        help="list only pull requests with this state",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="write to a file instead of stdout",
    )
    parser.add_argument(
        "--no-reviews", action="store_true",
        help="skip scanning for reviews given (fewer API calls)",
    )
    parser.add_argument(
        "--trend", action="store_true",
        help="compare this window against the one before it (doubles API calls)",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="bypass the local cache for fresh data",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
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
        "--cache-dir", type=Path, default=Path.home() / ".cache" / "prsnoop",
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
        "--format", "-f",
        choices=["table", "markdown", "csv", "json"],
        default="table",
    )
    cmp_p.add_argument(
        "--cache-dir", type=Path, default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    cmp_p.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return cmp_p


def build_org_parser() -> argparse.ArgumentParser:
    """Parser for the org subcommand."""
    org_p = argparse.ArgumentParser(
        prog="prsnoop org",
        description="Pulse report for a GitHub organization: who ships, what is hot.",
    )
    org_p.add_argument("org", help="GitHub organization or owner login")
    org_p.add_argument("--days", type=int, default=30)
    org_p.add_argument("--since", type=str, default=None)
    org_p.add_argument("--until", type=str, default=None)
    org_p.add_argument(
        "--format", "-f", choices=["table", "markdown", "json"], default="table"
    )
    org_p.add_argument(
        "--output", "-o", type=Path, default=None, help="write to a file"
    )
    org_p.add_argument(
        "--cache-dir", type=Path, default=Path.home() / ".cache" / "prsnoop",
        help="cache directory (default: ~/.cache/prsnoop)",
    )
    org_p.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return org_p


def cmd_org(args: argparse.Namespace) -> int:
    from prsnoop.org import fetch_org_pulse
    from prsnoop.render import render_org_markdown, render_org_table

    since = _validate_date(args.since, "--since") if args.since else None
    until = _validate_date(args.until, "--until") if args.until else None
    if args.days < 1:
        print("prsnoop: --days must be >= 1", file=sys.stderr)
        return 2
    if args.until and not args.since:
        print("prsnoop: --until requires --since", file=sys.stderr)
        return 2
    client = GitHubClient(
        cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}"
    )
    try:
        prs, pulse = fetch_org_pulse(
            client, args.org, days=args.days, since=since, until=until
        )
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
    client = GitHubClient(
        cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}"
    )
    try:
        prs, reviews, issues, _ = fetch_user_activity(
            client, args.user, days=args.days, include_reviews=True,
            since=since, until=until,
        )
    except (GitHubError, RateLimitExceeded) as exc:
        print(f"prsnoop: {exc}", file=sys.stderr)
        return 3
    activity = build_activity(
        args.user, prs, reviews, issues,
        window_days=args.days, since=since or "", until=until or "",
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
    client = GitHubClient(
        cache_dir=args.cache_dir, user_agent=f"prsnoop/{__version__}"
    )
    users = [args.user_a, args.user_b]
    activities: list[Activity] = []
    for user in users:
        try:
            prs, reviews, issues, _ = fetch_user_activity(
                client, user, days=args.days, include_reviews=False,
                org=args.org, since=since, until=until,
            )
        except (GitHubError, RateLimitExceeded) as exc:
            print(f"prsnoop: {exc}", file=sys.stderr)
            return 3
        activities.append(
            build_activity(
                user, prs, reviews, issues,
                window_days=args.days, since=since or "", until=until or "",
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
            f"{a.longest_streak_days}d", f"{b.longest_streak_days}d", "high",
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
            "--cache-dir", type=Path, default=Path.home() / ".cache" / "prsnoop",
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
    if raw and raw[0] == "org":
        org_args = build_org_parser().parse_args(raw[1:])
        logging.basicConfig(
            level=logging.DEBUG if org_args.verbose else logging.WARNING,
            format="%(levelname)s %(name)s: %(message)s",
        )
        return cmd_org(org_args)

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

    try:
        client = GitHubClient(
            cache_dir=args.cache_dir,
            user_agent=f"prsnoop/{__version__}",
        )
        prs, reviews, issues, fully_enriched = fetch_user_activity(
            client,
            args.user,
            days=args.days,
            include_reviews=not args.no_reviews,
            org=args.org,
            since=since,
            until=until,
        )
        activity = build_activity(
            args.user, prs, reviews, issues,
            window_days=args.days, since=since or "", until=until or "",
        )
        if args.trend:
            prev_since, prev_until = _previous_window(since, until, args.days)
            try:
                p_prs, p_reviews, p_issues, _ = fetch_user_activity(
                    client, args.user, days=args.days,
                    include_reviews=not args.no_reviews, org=args.org,
                    since=prev_since, until=prev_until,
                )
                prev_activity = build_activity(
                    args.user, p_prs, p_reviews, p_issues,
                    window_days=args.days, since=prev_since, until=prev_until,
                )
                trend = build_trend(activity.stats, prev_activity.stats)
                activity.trend = trend
            except (GitHubError, RateLimitExceeded) as exc:
                print(
                    f"prsnoop: trend window skipped: {exc}", file=sys.stderr
                )
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

    report_activity = activity
    if args.only:
        report_activity = replace(
            activity, prs=[pr for pr in activity.prs if pr.state == args.only]
        )
    rendered = RENDERERS[args.format](report_activity)
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
