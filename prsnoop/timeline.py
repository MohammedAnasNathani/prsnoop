"""Timeline: the window's activity as a chronological event stream.

Merges PRs, issues, and reviews into one dated stream with a visual bar,
ready for the terminal or markdown. Also computes week-by-week buckets.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from prsnoop.models import Activity, JsonDict

KIND_MARK = {"pr": "[PR]", "issue": "[IS]", "review": "[RV]", "merge": "[++]"}


@dataclass(slots=True)
class Event:
    """One dated activity event."""

    date: str          # YYYY-MM-DD
    kind: str          # pr | issue | review | merge
    repo: str
    title: str
    detail: str

    def to_dict(self) -> JsonDict:
        return {
            "date": self.date,
            "kind": self.kind,
            "repo": self.repo,
            "title": self.title,
            "detail": self.detail,
        }


@dataclass(slots=True)
class Timeline:
    """The merged event stream plus weekly buckets."""

    user: str
    events: list[Event] = field(default_factory=list)
    weeks: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "weeks": [{"week": w, "events": n} for w, n in self.weeks],
            "events": [e.to_dict() for e in self.events],
        }


def build_timeline(activity: Activity, limit: int = 200) -> Timeline:
    """Merge every record type into one reverse-chronological stream."""
    events: list[Event] = []
    for p in activity.prs:
        events.append(Event(
            p.created_at.strftime("%Y-%m-%d"), "pr", p.repo,
            f"#{p.number} {p.title}",
            f"+{p.additions}/-{p.deletions}",
        ))
        if p.state == "merged" and p.merged_at is not None:
            events.append(Event(
                p.merged_at.strftime("%Y-%m-%d"), "merge", p.repo,
                f"#{p.number} merged",
                f"{p.days_to_merge:.1f}d to merge" if p.days_to_merge is not None else "",
            ))
    for i in activity.issues:
        events.append(Event(
            i.created_at.strftime("%Y-%m-%d"), "issue", i.repo,
            f"#{i.number} {i.title}",
            "closed" if i.state == "CLOSED" else "open",
        ))
    for r in activity.reviews:
        events.append(Event(
            r.submitted_at.strftime("%Y-%m-%d"), "review", r.repo,
            f"#{r.pr_number} {r.pr_title}",
            r.state.lower(),
        ))
    events.sort(key=lambda e: e.date, reverse=True)

    weekly: dict[str, int] = {}
    for e in events:
        d = e.date
        # bucket by ISO week start (Monday): back up to the nearest Monday
        from datetime import date as _date
        dd = _date.fromisoformat(d)
        monday = dd.fromordinal(dd.toordinal() - dd.weekday()).isoformat()
        weekly[monday] = weekly.get(monday, 0) + 1
    weeks = sorted(weekly.items())

    return Timeline(user=activity.user, events=events[:limit], weeks=weeks)


SPARK = " .:;+=xX#"


def render_timeline_table(tl: Timeline, width: int = 60) -> str:
    lines = [f"prsnoop timeline | {tl.user}", ""]
    if tl.weeks:
        peak = max(n for _, n in tl.weeks) or 1
        lines.append("  weekly activity")
        for w, n in tl.weeks[-12:]:
            bar = "#" * max(1, int(n / peak * 20))
            lines.append(f"  {w}  {bar} {n}")
        lines.append("")
    lines.append(f"  events (newest first, capped at {len(tl.events)})")
    for e in tl.events[:40]:
        mark = KIND_MARK.get(e.kind, "[..]")
        title = e.title[:46]
        lines.append(f"  {e.date}  {mark:<5} {e.repo:<22} {title}")
    if len(tl.events) > 40:
        lines.append(f"  ... and {len(tl.events) - 40} more")
    return "\n".join(lines)


def render_timeline_markdown(tl: Timeline) -> str:
    out = [
        f"# Timeline: {tl.user}",
        "",
        "| Date | Kind | Repo | Event |",
        "|---|---|---|---|",
    ]
    for e in tl.events[:60]:
        title = e.title.replace("|", "\\|")
        out.append(
            f"| {e.date} | {KIND_MARK.get(e.kind, '..')} | {e.repo} "
            f"| {title} · {e.detail} |"
        )
    out.append("")
    return "\n".join(out)
