# prsnoop

[Website](https://mohammedanasnathani.github.io/prsnoop/) | [Install](#install) | [Compare with alternatives](#how-it-compares)

[![CI](https://github.com/MohammedAnasNathani/prsnoop/actions/workflows/ci.yml/badge.svg)](https://github.com/MohammedAnasNathani/prsnoop/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/prsnoop/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://github.com/astral-sh/ruff)

Pull request analytics from the command line. prsnoop reads a GitHub user's
pull requests, reviews, and issues through the public API and produces
reports in the terminal, Markdown, HTML, CSV, or JSON: merge rate, time to
merge percentiles, daily activity, streaks, repository and language
breakdowns.

```text
$ prsnoop simonw --days 30

prsnoop | simonw
window: last 30 days

  Pull requests      39
    merged           34
    open             5
    closed           0
  Reviews given      0
  Issues opened      28 (closed: 21)
  Lines changed      +16115 / -2137
  Merge rate         87%
  Merge time         median 0.0d, p90 0.2d
  Active days        22 (avg 1.77 PRs/day)
  Streaks            longest 7d, current 2d
  Repos              13
  Busiest day        2026-09-01 (14 items)
  Languages          Python 21, HTML 18

  Recent pull requests
  [merged] simonw/tools#331 Add video compressor tool using ffmpeg.wasm
  [  open] simonw/tools#330 Add WebP export to markdown-svg-renderer
  [merged] simonw/sqlite-utils#852 Python 3.15 rc2
  ...
```

The example above is real output for a public developer, generated with the
command shown.

## Why this tool exists

The GitHub profile page answers "how many squares turn green." It does not
answer the questions that come up in the real world:

- What share of my pull requests actually merged?
- How long do maintainers take to merge my work?
- Which projects am I actually invested in, and in what languages?
- What does the last month of work look like as a document I can send?

Contribution dashboards exist, but they are web applications: accounts,
onboarding tours, JavaScript, and pricing tiers. Most people who need these
numbers need them in a terminal or a file, in seconds, without a signup
flow.

prsnoop is that: one command, no runtime dependencies, output you can
paste anywhere.

## How it compares

| Need | prsnoop | gh CLI | OpenSauced | OSS Insight |
|---|---|---|---|---|
| Install size | one package, zero deps | large binary | web app | web app |
| Time to first report | one command | write your own jq pipeline | sign up, connect | browse to site |
| Time-to-merge percentiles | yes | manual | partial | repo focused |
| Daily activity and streaks | yes | manual | streaks only | no |
| Language mix | yes | manual | yes | yes |
| Org-scoped filtering | yes | manual | workspaces | collections |
| Compare two time windows | `snap --compare` | manual | no | no |
| Compare two people | `prsnoop compare` | manual | no | no |
| README badges | `--format badge` | shields.io service | no | no |
| Works offline after first run | cached | no | no | no |
| Output formats | table, md, html, csv, json | text | web views | web views, API |
| Open source | MIT | MIT | open core | MIT |

Notes on the field:

- **gh CLI** can list PRs, but turning them into a report means writing
  jq/GraphQL pipelines every time. prsnoop is the pipeline, packaged.
- **OpenSauced** is a funded product with dashboards, workspaces, and
  browser extensions. It shines at organization-level insights. It is not
  something you can run in a terminal over SSH or embed in a build.
- **OSS Insight** (by PingCAP) analyzes billions of GitHub events, mostly
  for repository and ecosystem research. It is not a personal contribution
  report generator.
- **GitHub profile page** shows counts. No rates, no timing, no documents.

The gap: instant, scriptable, personal PR analytics with zero setup.
That is prsnoop.

## Install

```bash
pip install prsnoop
```

From source:

```bash
git clone https://github.com/MohammedAnasNathani/prsnoop
cd prsnoop && pip install .
```

## Usage

```bash
prsnoop simonw                          # terminal table, last 30 days
prsnoop simonw --days 90                # wider window
prsnoop simonw --since 2026-08-01 --until 2026-08-31
prsnoop simonw --org vueuse             # one organization only
prsnoop simonw -f markdown -o report.md
prsnoop simonw -f html -o report.html   # standalone page, no assets
prsnoop simonw -f csv -o report.csv     # one row per PR
prsnoop simonw -f json -o report.json   # full snapshot with stats
prsnoop simonw -f badge -o badges.md     # embeddable SVG badges
prsnoop compare antfu simonw --days 30   # head-to-head, same window
prsnoop simonw --no-reviews             # fewer API calls
prsnoop auth                            # token and rate limit status
prsnoop auth --clear-cache              # empty the local cache
prsnoop snap simonw -o june.json        # frozen snapshot
prsnoop snap simonw --compare june.json # delta since the snapshot
```

Example reports generated by the tool itself live in
[examples/](examples/): [Markdown](examples/simonw_30d.md),
[HTML](examples/simonw_30d.html), [CSV](examples/simonw_30d.csv),
[badges](examples/antfu_badges.md).

### Badges

`--format badge` writes four flat-square SVG badges (PRs, merged, merge
rate, longest streak) as Markdown data URIs. No badge service, no network
dependency once generated: the SVGs live in your README.

### GitHub Actions

A reusable composite action ships in this repo. One step in any workflow:

```yaml
- uses: MohammedAnasNathani/prsnoop/.github/actions/prsnoop-report@main
  with:
    user: your-username
    days: "7"
    token: ${{ secrets.GITHUB_TOKEN }}
```

It renders the report into the run summary and drops the file as an
artifact. See `.github/workflows/weekly-report.yml` for a scheduled
example.

### Token

Without a token you get 60 core requests per hour and search results are
hidden entirely. With a token: 5000 per hour and full search.

```bash
export PRSNOOP_TOKEN=ghp_xxx     # or GITHUB_TOKEN
```

PowerShell: `$env:PRSNOOP_TOKEN = "ghp_xxx"`. Never hardcode tokens in
scripts; keep them in the environment.

prsnoop sends the token only to api.github.com over HTTPS. API responses
are cached under `~/.cache/prsnoop` and revalidated with ETags, so repeat
runs cost almost nothing against your rate limit.

## What it measures

| Metric | Definition |
|---|---|
| Pull requests | PRs authored in the window, split merged / open / closed |
| Merge rate | merged / authored |
| Merge time | created to merged; median and p90 across merged PRs |
| Reviews given | formal reviews and substantive comments on other authors' PRs |
| Issues | issues authored, with closed count |
| Lines changed | additions and deletions across your PRs |
| Active days | UTC days with any PR, issue, or review |
| Streaks | longest and current runs of consecutive active days |
| Languages | PR count by each repository's primary language |
| Top repositories | PR count per repo, ranked |

Large accounts note: beyond 300 PRs in one window the tool stops per-PR
enrichment and marks lines-changed totals as partial, so a report on a very
active account never runs for hours.

## Exit codes

0 success, 2 usage error, 3 API error, 4 rate limited (set a token).

## Development

```bash
git clone https://github.com/MohammedAnasNathani/prsnoop && cd prsnoop
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest          # 74 tests, all offline
ruff check .     # lint
mypy             # strict type checking
```

CI runs the same three steps on Windows, macOS, and Ubuntu across Python
3.10 to 3.14 on every push and pull request.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules: zero runtime
dependencies, no network in tests, small public API, deterministic
renderers.

### Releasing

Tagging a version (`git tag v1.2.0 && git push origin v1.2.0`) makes CI run
the full checks, build the package, and attach it to a GitHub release.
Distributions also go to PyPI automatically once the repository has a
`PYPI_API_TOKEN` secret (PyPI account, API token scoped to the prsnoop
project, added under Settings, Secrets and variables, Actions).

## License

MIT
