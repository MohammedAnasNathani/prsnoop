# Changelog

All notable changes to prsnoop are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `prsnoop live <user>`: interactive single-fetch PR browser for a TTY,
  with paging, table/json toggling, and one-time fetch semantics.

## [1.3.0] - 2026-09-08

### Added
- `prsnoop org <org>`: organization pulse report. One search covers every
  PR opened in the org: totals, unique authors and repositories, median
  time to merge, top-author and hot-repo leaderboards, an activity chart,
  and the recent PR feed. Table, Markdown, and JSON.
- `--trend`: compares the current window against the one before it, same
  size, same clock. Every report format shows the deltas with direction
  and percent; median merge time knows that faster is better.
- Activity sparkline: a one-line ASCII chart of day-by-day totals in
  every table report, `#` at the peak, `.` on quiet days.
- `compare` gains `-f csv` and `-f json` for scripts and spreadsheets.
- HTML reports redesigned: stat cards, an inline SVG daily chart with
  tooltips, trend arrows, and a dark theme that follows the system.

[1.3.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.3.0

## [1.2.0] - 2026-09-08

### Added
- Badge generation (`--format badge`): four flat-square SVG badges (PRs,
  merged, merge rate, longest streak) emitted as ready-to-paste Markdown
  data URIs. No hosting service needed.
- `prsnoop compare user_a user_b`: side-by-side comparison over one shared
  window, in table and Markdown.
- Reusable composite GitHub Action (`.github/actions/prsnoop-report`) plus a
  weekly scheduled workflow that files a report as an artifact.
- Example reports and badge files for three public developers.

### Fixed
- Review discovery no longer breaks with a 422 on prolific reviewers:
  the reviewed-by search is date-bounded to the report window.


## [1.1.0] - 2026-09-07

### Added
- Timing analytics: p90, fastest, and slowest time to merge alongside the median.
- Daily activity breakdown per UTC day: PRs, merges, issues, reviews.
- Longest and current activity streaks.
- Language mix, derived from each repository's primary language.
- Busiest day, active days, average PRs per active day, issue close counts.
- `--org` filter to scope a report to one organization or owner.
- `--since` / `--until` absolute date windows (YYYY-MM-DD).
- `prsnoop auth`: token detection, core and search rate limit status, cache clearing.
- `prsnoop snap`: frozen JSON snapshots with `--compare` to diff two windows.
- Per-PR labels, comment counts, and draft state in records and CSV.
- Competitor comparison table in the README (gh CLI, OpenSauced, OSS Insight).
- Enrichment budget: beyond 300 PRs in a window, lines-changed totals are
  marked partial instead of spending hours of API budget.

### Changed
- All output is plain ASCII so reports survive every terminal and legacy
  Windows console. States read merged / open / closed in text.
- Markdown and HTML reports show timing, streak, language, and daily tables.
- CSV now includes labels, comments, and language columns.
- Test suite grown to 63 offline tests.

## [1.0.0] - 2026-09-07

First stable release.

### Added
- `prsnoop <user>` CLI with a `--days` look-back window (default 30).
- Five output formats: `table`, `markdown`, `html`, `csv`, `json`,
  each writable with `-o/--output`.
- Contribution metrics: PRs authored/merged/open/closed, reviews given,
  issues opened, lines added/deleted, merge rate, median days-to-merge,
  distinct repos, top repositories.
- Zero-dependency GitHub REST client with token auth
  (`PRSNOOP_TOKEN` / `GITHUB_TOKEN`), pagination, and an on-disk cache
  with ETag revalidation (`~/.cache/prsnoop`).
- `--no-reviews` and `--no-cache` flags; `--version`; `--verbose`.
- Distinct exit codes: 0 ok, 2 usage, 3 API error, 4 rate limit.
- 47 offline unit tests, ruff + mypy (strict) clean, CI on push and PR.

[1.3.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.3.0
[1.2.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.2.0
[1.1.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.1.0
[1.0.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.0.0
