"""Achievements engine: 40+ unlockable badges computed from one Activity.

Each achievement checks a predicate against the snapshot and reports
locked/unlocked with progress. Rarity tiers (common, rare, epic, legendary)
make the display feel like a game without any external service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from prsnoop.models import Activity, JsonDict, PRRecord


@dataclass(slots=True)
class Achievement:
    """One achievement definition plus its live evaluation."""

    key: str
    name: str
    description: str
    rarity: str          # common | rare | epic | legendary
    icon: str
    unlocked: bool
    progress: str        # human-readable progress toward the goal

    def to_dict(self) -> JsonDict:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "rarity": self.rarity,
            "icon": self.icon,
            "unlocked": self.unlocked,
            "progress": self.progress,
        }


RARITY_ORDER = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}


def _prs(activity: Activity) -> list[PRRecord]:
    return activity.prs


def _merged(activity: Activity) -> list[PRRecord]:
    return [p for p in activity.prs if p.state == "merged"]


def _evaluate(activity: Activity) -> list[Achievement]:
    s = activity.stats
    prs = _prs(activity)
    merged = _merged(activity)
    out: list[Achievement] = []

    def add(
        key: str,
        name: str,
        desc: str,
        rarity: str,
        icon: str,
        unlocked: bool,
        progress: str,
    ) -> None:
        out.append(Achievement(key, name, desc, rarity, icon, unlocked, progress))

    # ---- volume achievements
    n = s.prs_authored
    add("first_pr", "First Blood", "Opened your first pull request", "common", "🩸",
        n >= 1, f"{max(n, 0)}/1")
    add("prs_10", "Double Digits", "Opened 10 pull requests", "common", "🔟",
        n >= 10, f"{min(n, 10)}/10")
    add("prs_25", "Quarter Century", "Opened 25 pull requests", "rare", "award_strong",
        n >= 25, f"{min(n, 25)}/25")
    add("prs_50", "Half Century", "Opened 50 pull requests", "epic", "award",
        n >= 50, f"{min(n, 50)}/50")
    add("prs_100", "Centurion", "Opened 100 pull requests", "legendary", "battle",
        n >= 100, f"{min(n, 100)}/100")
    add("prs_250", "Machine", "Opened 250 pull requests", "legendary", "machine",
        n >= 250, f"{min(n, 250)}/250")

    # ---- merge achievements
    m = s.prs_merged
    add("first_merge", "Landed", "Got your first PR merged", "common", "check",
        m >= 1, f"{max(m, 0)}/1")
    add("merges_25", "Reliable", "25 merged pull requests", "rare", "check_check",
        m >= 25, f"{min(m, 25)}/25")
    add("merges_100", "Merge Machine", "100 merged pull requests", "epic", "factory",
        m >= 100, f"{min(m, 100)}/100")
    add("perfect_rate", "Flawless", "100% merge rate with 5+ PRs", "epic", "gem",
        n >= 5 and s.merge_rate >= 0.999, f"{s.merge_rate * 100:.0f}% of {n}")
    add("speed_demon", "Speed Demon", "A PR merged in under 1 hour", "rare", "bolt",
        any((p.days_to_merge or 99) < 1 / 24 for p in merged), "fastest merge checked")
    add("same_day", "Same-Day", "5+ PRs merged within 24h of opening", "epic", "clock",
        sum(1 for p in merged if (p.days_to_merge or 99) <= 1) >= 5,
        f"{sum(1 for p in merged if (p.days_to_merge or 99) <= 1)}/5")

    # ---- lines achievements
    la = s.lines_added
    add("lines_1k", "Kilo Contributor", "1,000+ lines added", "common", "pen",
        la >= 1000, f"{min(la, 1000):,}/1,000")
    add("lines_10k", "Ten K Club", "10,000+ lines added", "rare", "books",
        la >= 10000, f"{min(la, 10000):,}/10,000")
    add("lines_100k", "Mega Rewrite", "100,000+ lines added", "legendary", "volcano",
        la >= 100000, f"{min(la, 100000):,}/100,000")
    biggest = max((p.additions + p.deletions for p in prs), default=0)
    add("giant_pr", "The Kraken", "A single PR over 10,000 lines", "epic", "kraken",
        biggest >= 10000, f"{biggest:,}/10,000")
    add("tiny_pr", "Surgical", "A merged PR under 10 lines", "common", "knife",
        any(p.state == "merged" and 0 < (p.additions + p.deletions) < 10 for p in merged),
        "smallest merged checked")
    add("deletionist", "Deletionist", "Deleted more code than you added", "rare", "broom",
        la > 0 and s.lines_deleted > la, f"-{s.lines_deleted:,} vs +{la:,}")

    # ---- streak / rhythm achievements
    add("streak_3", "Warming Up", "3-day activity streak", "common", "walk",
        s.longest_streak_days >= 3, f"{min(s.longest_streak_days, 3)}/3 days")
    add("streak_7", "Week Warrior", "7-day activity streak", "rare", "run",
        s.longest_streak_days >= 7, f"{min(s.longest_streak_days, 7)}/7 days")
    add("streak_14", "Fortnight", "14-day activity streak", "epic", "bike",
        s.longest_streak_days >= 14, f"{min(s.longest_streak_days, 14)}/14 days")
    add("streak_30", "Iron Man", "30-day activity streak", "legendary", "shield",
        s.longest_streak_days >= 30, f"{min(s.longest_streak_days, 30)}/30 days")
    add("consistent", "Metronome", "Active on 20+ days in the window", "rare", "drum",
        s.active_days >= 20, f"{min(s.active_days, 20)}/20 days")
    add("momentum_up", "Accelerating", "Second half stronger than the first", "rare", "up",
        s.momentum == "accelerating", s.momentum or "no data")
    add("momentum_hold", "Steady Hand", "Held steady momentum", "common", "level",
        s.momentum == "steady", s.momentum or "no data")

    # ---- breadth achievements
    add("polyglot_3", "Polyglot", "Shipped code in 3+ languages", "common", "globe",
        s.distinct_languages >= 3, f"{min(s.distinct_languages, 3)}/3 languages")
    add("polyglot_6", "Language Collector", "Shipped code in 6+ languages", "epic", "babel",
        s.distinct_languages >= 6, f"{min(s.distinct_languages, 6)}/6 languages")
    add("repos_5", "Explorer", "Contributed to 5+ repositories", "common", "map",
        s.distinct_repos >= 5, f"{min(s.distinct_repos, 5)}/5 repos")
    add("repos_15", "Nomad", "Contributed to 15+ repositories", "epic", "compass",
        s.distinct_repos >= 15, f"{min(s.distinct_repos, 15)}/15 repos")
    add("spread", "Generalist", "No single repo holds more than 40% of your PRs",
        "rare", "scatter",
        bool(prs) and max(
            sum(1 for p in prs if p.repo == r) for r in {p.repo for p in prs}
        ) / len(prs) <= 0.4 if prs else False,
        "distribution checked")

    # ---- collaboration achievements
    add("reviewer_5", "Reviewer", "Left 5 reviews on other people's PRs",
        "common", "magnifier", s.reviews_given >= 5, f"{min(s.reviews_given, 5)}/5")
    add("reviewer_25", "Review Hero", "Left 25 reviews", "epic", "hero",
        s.reviews_given >= 25, f"{min(s.reviews_given, 25)}/25")
    add("issues_5", "Bug Hunter", "Opened 5 issues", "common", "bug",
        s.issues_opened >= 5, f"{min(s.issues_opened, 5)}/5")
    add("issues_20", "Quality Sentinel", "Opened 20 issues", "rare", "watch",
        s.issues_opened >= 20, f"{min(s.issues_opened, 20)}/20")
    add("closer", "Finisher", "10+ of your issues got closed", "rare", "lock",
        s.issues_closed >= 10, f"{min(s.issues_closed, 10)}/10")

    # ---- exotic achievements
    add("night_owl", "Night Owl", "Opened a PR between midnight and 5am", "rare", "moon",
        any(0 <= p.created_at.hour < 5 for p in prs), "commit hours scanned")
    add("early_bird", "Early Bird", "Opened a PR before 6am", "rare", "sunrise",
        any(5 <= p.created_at.hour < 6 for p in prs), "commit hours scanned")
    add("weekend", "Weekend Warrior", "Opened PRs on both Saturday and Sunday", "common",
        "calendar",
        bool({p.created_at.weekday() for p in prs} & {5, 6})
        and len({p.created_at.weekday() for p in prs} & {5, 6}) == 2,
        "weekend days checked")
    add("marathon_pr", "Marathon", "10+ PRs in a single day", "epic", "medal",
        s.busiest_day_count >= 10, f"{min(s.busiest_day_count, 10)}/10 in one day")
    add("busy_day", "Power Day", "5+ items of activity in one day", "common", "pop",
        s.busiest_day_count >= 5, f"{min(s.busiest_day_count, 5)}/5 in one day")
    add("open_standing", "Work in Flight", "5+ PRs open right now", "common", "kite",
        s.prs_open >= 5, f"{min(s.prs_open, 5)}/5 open")
    add("big_picture", "Big Picture", "Contributed across 3+ languages and 5+ repos",
        "epic", "orbit", s.distinct_languages >= 3 and s.distinct_repos >= 5,
        f"{s.distinct_languages} langs / {s.distinct_repos} repos")
    add("top_repo", "Home Turf", "One repo with 10+ of your PRs", "common", "home",
        bool(s.top_repos) and s.top_repos[0][1] >= 10,
        f"{s.top_repos[0][1] if s.top_repos else 0}/10 in top repo")

    # ---- v2.2 expansion
    add("p90_fast", "Ninety Percent", "p90 merge time under 3 days", "epic",
        "clock2", s.p90_days_to_merge is not None and s.p90_days_to_merge < 3,
        f"p90 {s.p90_days_to_merge if s.p90_days_to_merge is not None else '—'}d")
    add("no_close", "Never Closed", "10+ PRs and none closed unmerged", "rare",
        "shield2", s.prs_authored >= 10 and s.prs_closed_unmerged == 0,
        f"{s.prs_closed_unmerged} closed unmerged")
    add("multi_monster", "Kraken Tamer", "3+ PRs over 1,000 lines each", "epic",
        "tentacle",
        sum(1 for p in prs if p.additions + p.deletions >= 1000) >= 3,
        f"{sum(1 for p in prs if p.additions + p.deletions >= 1000)}/3")
    add("daily_double", "Daily Double", "2+ PRs merged on the same day", "common",
        "dice",
        any(da.merged >= 2 for da in s.day_activity),
        "merge days scanned")
    day_repos: dict[str, set[str]] = {}
    for p in prs:
        day_repos.setdefault(p.created_at.strftime("%Y-%m-%d"), set()).add(p.repo)
    add("wide_net", "Wide Net", "Activity across 3+ repos in one day",
        "epic", "star", any(len(v) >= 3 for v in day_repos.values()),
        "repo spread scanned")
    add("half_open", "Balanced Load", "5+ open and 5+ merged", "common", "scale",
        s.prs_open >= 5 and s.prs_merged >= 5,
        f"{s.prs_open} open / {s.prs_merged} merged")
    add("comment_magnet", "Comment Magnet", "50+ comments across your PRs",
        "rare", "chat", sum(p.comments for p in prs) >= 50,
        f"{min(sum(p.comments for p in prs), 50)}/50 comments")
    add("debate_champ", "Debate Champion", "One PR with 15+ comments", "epic",
        "mic", max((p.comments for p in prs), default=0) >= 15,
        f"{max((p.comments for p in prs), default=0)}/15 on one PR")
    add("long_haul", "Long Haul", "A PR merged after 30+ days of review",
        "rare", "route",
        any((p.days_to_merge or 0) >= 30 for p in merged),
        f"{max((p.days_to_merge or 0) for p in merged) if merged else 0:.0f}/30d")
    add("clean_window", "Clean Sweep", "Every opened PR merged (3+)", "rare",
        "broom2", len(prs) >= 3 and len(merged) == len(prs),
        f"{len(merged)}/{len(prs)} merged")
    add("lines_50k", "Fifty K", "50,000+ lines added", "legendary", "mount",
        la >= 50000, f"{min(la, 50000):,}/50,000")
    add("issues_50", "Fifty Filed", "50+ issues opened", "legendary", "pad",
        s.issues_opened >= 50, f"{min(s.issues_opened, 50)}/50")
    add("reviews_100", "Review Centurion", "100 reviews given", "legendary",
        "scales", s.reviews_given >= 100, f"{min(s.reviews_given, 100)}/100")
    add("merge_500", "Five Hundred", "500 merged PRs", "legendary", "crown",
        m >= 500, f"{min(m, 500)}/500")
    add("repos_30", "Cartographer", "Contributed to 30+ repositories", "legendary",
        "atlas", s.distinct_repos >= 30, f"{min(s.distinct_repos, 30)}/30 repos")
    add("langs_10", "Decalinguist", "Shipped code in 10+ languages", "legendary",
        "prism", s.distinct_languages >= 10,
        f"{min(s.distinct_languages, 10)}/10 languages")
    add("streak_50", "Unbroken", "50-day activity streak", "legendary", "chain",
        s.longest_streak_days >= 50, f"{min(s.longest_streak_days, 50)}/50 days")
    add("double_kraken", "Double Kraken", "Two PRs over 10,000 lines", "legendary",
        "hydra",
        sum(1 for p in prs if p.additions + p.deletions >= 10000) >= 2,
        f"{sum(1 for p in prs if p.additions + p.deletions >= 10000)}/2")
    add("momentum_leg", "Rocket Fuel", "Accelerating with 15+ PRs", "legendary",
        "rocket", s.momentum == "accelerating" and s.prs_authored >= 15,
        f"{s.prs_authored} prs · {s.momentum or 'no data'}")

    return out


def unlock_all(activity: Activity) -> list[Achievement]:
    """Evaluate every achievement for one activity snapshot."""
    return _evaluate(activity)


@dataclass(slots=True)
class AchievementReport:
    """The full achievement board for one user."""

    user: str
    generated_at: datetime
    achievements: list[Achievement]
    score: int  # points earned

    @property
    def unlocked(self) -> list[Achievement]:
        return [a for a in self.achievements if a.unlocked]

    @property
    def locked(self) -> list[Achievement]:
        return [a for a in self.achievements if not a.unlocked]

    @property
    def completion(self) -> float:
        if not self.achievements:
            return 0.0
        return len(self.unlocked) / len(self.achievements) * 100

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "score": self.score,
            "completion_pct": round(self.completion, 1),
            "achievements": [a.to_dict() for a in self.achievements],
        }


POINTS = {"common": 10, "rare": 25, "epic": 50, "legendary": 100}


def build_report(activity: Activity) -> AchievementReport:
    board = _evaluate(activity)
    score = sum(POINTS.get(a.rarity, 0) for a in board if a.unlocked)
    return AchievementReport(
        user=activity.user,
        generated_at=activity.generated_at or datetime.now(timezone.utc),
        achievements=board,
        score=score,
    )


# ------------------------------------------------------------------ renders

_ICONS_ASCII = {
    "award_strong": "(**)", "award": "(A)", "battle": "(B)", "machine": "[M]",
    "check": "(v)", "check_check": "(vv)", "gem": "<>", "bolt": ">>", "clock": "(o)",
    "factory": "[F]", "kraken": "(K)", "knife": "-=", "broom": "/\\", "pen": "--",
    "books": "|||", "volcano": "/^\\", "walk": "..", "run": "...", "bike": "o-o",
    "shield": "[D]", "drum": "(d)", "up": "^^", "level": "--", "globe": "(G)",
    "babel": "(B)", "map": "[+]", "compass": "(C)", "scatter": ":", "magnifier": "(Q)",
    "hero": "(H)", "bug": "(b)", "watch": "(w)", "lock": "(L)", "moon": "( )",
    "sunrise": "/)", "calendar": "[7]", "medal": "(m)", "pop": "*", "kite": "<",
    "orbit": "(O)", "home": "[H]",
}


def render_board_table(rep: AchievementReport) -> str:
    lines = [
        f"prsnoop achievements | {rep.user}",
        "",
        f"  SCORE {rep.score:5d} pts   {len(rep.unlocked)}/{len(rep.achievements)} unlocked"
        f" ({rep.completion:.0f}%)",
        "",
        "  UNLOCKED",
    ]
    for a in rep.unlocked:
        icon = _ICONS_ASCII.get(a.icon, "(*)")
        lines.append(f"   {icon:<5} {a.name:<18} {a.rarity:<9} {a.description}")
    if not rep.unlocked:
        lines.append("   (none yet)")
    lines += ["", "  NEXT UP"]
    for a in rep.locked[:10]:
        icon = _ICONS_ASCII.get(a.icon, "(*)")
        lines.append(f"   {icon:<5} {a.name:<18} {a.rarity:<9} {a.progress}")
    return "\n".join(lines)


def render_board_markdown(rep: AchievementReport) -> str:
    out = [
        f"# Achievements: {rep.user}",
        "",
        f"**{rep.score} points** · {len(rep.unlocked)}/{len(rep.achievements)} unlocked"
        f" ({rep.completion:.0f}%)",
        "",
        "| | Achievement | Rarity | Status |",
        "|---|---|---|---|",
    ]
    for a in rep.achievements:
        mark = "unlocked" if a.unlocked else f"locked ({a.progress})"
        out.append(f"| {a.icon} | **{a.name}** | {a.rarity} | {mark} |")
    out.append("")
    return "\n".join(out)


def render_board_json(rep: AchievementReport) -> str:
    import json

    return json.dumps(rep.to_dict(), indent=2, ensure_ascii=True)
