# Changelog

All notable changes to prsnoop are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

## [1.6.0] - 2026-09-08

### Added
- `prsnoop card [user]`: a shareable 640x340 SVG stat card for READMEs.
  Header with avatar, five big numbers (PRs, merged, merge rate, reviews,
  streak), a sparkline of the whole window, and top repositories. Dark
  and light themes, hand-built SVG, no image service.
- `prsnoop radar owner/repo`: maintainer triage radar. Every open pull
  request ranked by waiting age, bucketed fresh, aging, stale, ancient,
  with a quiet count for PRs nobody has touched. Table, Markdown, JSON,
  CSV.
- `prsnoop changelog owner/repo`: release notes from merged pull
  requests, grouped into Breaking changes, Added, Fixed, Performance,
  and more by label and conventional-commit prefix. `--tag v1.2.0`
  resolves the tag date for you. Paste-ready Markdown or JSON.
- `prsnoop ci [user]`: contribution quality gates. Minimum PRs, merged,
  reviews, merge rate, and a merge-latency ceiling; writes a GitHub step
  summary when `$GITHUB_STEP_SUMMARY` is set and exits 1 when a gate
  fails.
- `prsnoop watch [user]`: live ANSI terminal dashboard. Refetches every
  N seconds, redraws, flags new pull requests, and rings the bell when
  one lands. `--once` renders a single frame for demos.
- `prsnoop replay SNAPSHOT`: re-render any report, or the wrapped
  superlatives, from a saved snapshot with zero network. Every model now
  round-trips through JSON, so snapshots are fully reproducible offline.
- Wrapped superlatives extended: fastest merge, slowest merge, and most
  discussed PR join the year in review.

## [1.5.0] - 2026-09-09

### Added
- `prsnoop wrapped [user]`: the year in review. Biggest patch, busiest
  month, longest streak, one-PR cadence, top repo and language, favorite
  weekday. Table, Markdown, or JSON.
- `prsnoop readme [user]`: paste-ready GitHub profile README section.
  Badges, stats table, momentum, top repositories, generated locally.
- Contribution calendar: a GitHub-style heatmap in every HTML report for
  windows over 45 days, one cell per day, greener means more shipped.
- `prsnoop serve` takes multiple targets: `prsnoop serve simonw
  org:vueuse repo:psf/requests` serves one dashboard with a tab per
  target, each with its own page and JSON route.
- `prsnoop serve [user]`: live local dashboard. A stdlib HTTP server on
  127.0.0.1 renders a fresh report on every request, auto-refreshes every
  five minutes, and exposes the full snapshot at /api/report plus
  /health for scripts. Nothing leaves the machine.
- `prsnoop team u1 u2 ...`: leaderboard across any number of contributors
  over one window, ranked by merged PRs. Table, Markdown, CSV, JSON.
- `prsnoop export [user]`: one command writes the whole report pack,
  txt, md, html, csv, json, and badges, into a dated folder.
- Momentum: every report now says whether the window is accelerating,
  steady, or slowing, with the second-half versus first-half delta.
- Org and repo pulses speak every format: html, csv, and four pulse
  badges (opened, merged, rate, authors) join table, markdown, and json.

### Fixed
- Transient failures no longer kill a report: server errors, network
  hiccups, and GitHub secondary rate limits (the abuse-detection 429s
  that carry Retry-After) are retried with backoff. A hard rate-limit
  exhaustion still fails fast.

[1.5.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.5.0

## [1.4.0] - 2026-09-09

### Added
- `prsnoop repo owner/name`: maintainer mode. The pulse report aimed at a
  single repository, so a maintainer sees who is contributing, what the
  merge backlog looks like, and how fast the project lands work.
- `prsnoop me`: resolves your own login from the token and reports on
  you. No username typing.
- Where your work lands: per-repository merge rate and median time to
  merge for every repo with two or more PRs in the window, in table,
  Markdown, and HTML. The answer to "which projects actually value my
  patches".
- PR size profile: typical PR size as a letter grade plus the XS through
  XL distribution over changed lines.
- `--last week|month|quarter|year`: window presets instead of counting
  days.

### Fixed
- Reviews on long-lived PRs no longer leak outside the report window.
  Previously a review submitted months ago on a recently-updated PR
  inflated review counts and dragged the daily chart back in time.

[1.5.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.5.0
[1.4.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.4.0

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

[1.4.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.4.0
[1.3.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.3.0
[1.2.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.2.0
[1.1.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.1.0
[1.0.0]: https://github.com/MohammedAnasNathani/prsnoop/releases/tag/v1.0.0
