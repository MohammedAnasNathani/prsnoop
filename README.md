# prsnoop

[![CI](https://github.com/MohammedAnasNathani/prsnoop/actions/workflows/ci.yml/badge.svg)](https://github.com/MohammedAnasNathani/prsnoop/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/prsnoop/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-zero-2ea043)](https://github.com/MohammedAnasNathani/prsnoop)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://docs.astral.sh/ruff/)

One command, one GitHub username, a full report of what their pull requests
actually did. v2 adds a health score, 40+ achievements, pace forecasting,
natural-language Q&A, a full-screen live TUI, review networks, digests, and
a one-page HTML report, on top of the classic table, Markdown, HTML, CSV,
JSON, and badge outputs. Still zero runtime dependencies.

```text
$ prsnoop simonw --days 30

prsnoop | simonw
window: last 30 days

  Pull requests      42
    merged           37
    open             5
    closed           0
  Reviews given      7
  Issues opened      32 (closed: 25)
  Lines changed      +17593 / -2414
  Merge rate         88%
  Merge time         median 0.0d, p90 0.0d
  Active days        22 (avg 1.91 PRs/day)
  Streaks            longest 6d, current 3d
  Repos              13
  Busiest day        2026-09-01 (18 items)
  Languages          Python 23, HTML 19

  Recent pull requests
  [merged] datasette/datasette-agent#40 Select a model when you start a conversation
  [merged] simonw/llm#1674 httpx2-pytest>=2, refs #1673
  [merged] simonw/tools#332 Video compressor: filename field, poster JPE
  [merged] simonw/tools#331 Add video compressor tool using ffmpeg.wasm
  ...
```

Real output, real user, one command, a few seconds.

## Contents

- [Install](#install)
- [Usage](#usage)
- [Output formats](#output-formats)
- [Badges](#badges)
- [GitHub Actions](#github-actions)
- [Tokens and caching](#tokens-and-caching)
- [What it measures](#what-it-measures)
- [How it compares](#how-it-compares)
- [Development](#development)
- [License](#license)

## Install

```bash
pip install prsnoop
```

Or from source:

```bash
git clone https://github.com/MohammedAnasNathani/prsnoop
cd prsnoop && pip install .
```

prsnoop runs on Python 3.10 through 3.14, on macOS, Linux, and Windows.
It imports nothing outside the standard library, so it lands clean in any
virtualenv, container, or CI runner.

## Usage

Point it at any public GitHub user:

```bash
prsnoop simonw                          # last 30 days, terminal table
prsnoop me                              # yourself, from your token
prsnoop simonw --last quarter           # week / month / quarter / year
prsnoop simonw --trend                  # plus delta vs the window before
prsnoop simonw --since 2026-08-01 --until 2026-08-31
prsnoop simonw --org vueuse             # one organization only
prsnoop simonw --no-reviews             # fewer API calls
```

Every table report now carries a one-line activity chart, `#` at the peak,
`.` on quiet days, so the shape of the month is visible at a glance:

```text
  Activity chart     .+:;+.X...+.=.:#X...=;
    2026-08-09 to 2026-09-08, # peak, . quiet
```

Check the pulse of a whole organization, not just one person. Who ships,
what is hot, how fast merges land:

```text
$ prsnoop org vueuse --days 30

prsnoop org | vueuse
window: 2026-08-09 to 2026-09-08

  PRs opened        42
    merged         10
    open           27
  Authors           22
  Repos             1
  Median merge      3.6d

  Top authors
    lazerg               8
    haoku123             7
    ...
```

Compare two people over the same window and clock (table, Markdown,
CSV, or JSON):

```text
$ prsnoop compare antfu simonw --days 30

  metric             antfu          simonw
  ------------------ -------------- --------------
  pull requests                 10              42
  merged                         0              37
  merge rate                    0%             88%
  issues opened                  1              32
  median merge                    -            0.0d
  longest streak                 3d              6d
  repos                          8              13
```

Run a live local dashboard. Fresh report on every request, auto-refresh,
JSON at `/api/report`, 127.0.0.1 only, nothing leaves the machine. Mix
targets, one tab each:

```bash
prsnoop serve simonw                          # http://127.0.0.1:8642
prsnoop serve antfu org:vueuse repo:psf/requests
```

Rank a whole team over one window, any number of contributors:

```text
$ prsnoop team antfu simonw gvanrossum --last month

prsnoop team | ranked by merged
window: last 30 days

   #  user                 prs    merged      rate    issues    median    streak     repos
  --  --------------  --------  --------  --------  --------  --------  --------  --------
   1  simonw                33        29       88%        59      0.0d        8d        12 *
   2  antfu                  4         3       75%         1      0.0d        3d         4
```

One command, the whole report pack, into a dated folder:

```bash
prsnoop export simonw --trend      # txt, md, html, csv, json, badges
```

Every report also carries a momentum line, accelerating, steady, or
slowing, computed from the second half of the window against the first.

Maintainer mode: the same pulse for one repository. Who is contributing
to your project, how big the open backlog is, how fast merges land:

```text
$ prsnoop repo psf/requests --days 30

prsnoop repo | psf/requests
window: 2026-08-09 to 2026-09-08

  PRs opened        6
    merged         5
    open           1
  Authors           2
  Median merge      0.0d

  Top authors
    dependabot[bot]      5
    nateprewitt          1
```

Ask for the year in review. The superlatives a profile page never shows:

```text
$ prsnoop wrapped simonw

  THE YEAR IN PULL REQUESTS

  Pull requests      931 (merged 812)
  Lines changed      +1,454,053
  Longest streak     43 days
  Cadence            one PR every 0.4 days
  Busiest month      2025-12
  Busiest repo       simonw/tools
  Top language       Python
  Biggest patch      569,672 lines
  Favorite day       Wednesday
```

Generate a paste-ready GitHub profile README section, badges, stats
table, momentum, top repositories:

```bash
prsnoop readme your-username -o profile-section.md
```

Drop a shareable stat card into your README. One self-contained SVG,
hand-built, no image service, no external request, dark or light:

```bash
prsnoop card your-username -o card.svg           # 640x340, sparkline built in
prsnoop card your-username --theme light -o card.svg
```

Maintainer triage radar: every open pull request on a repository, ranked
by waiting age, sorted into fresh, aging, stale, and ancient buckets. The
Monday-morning list, plus a quiet count for PRs nobody has touched:

```text
$ prsnoop radar simonw/datasette

prsnoop radar | simonw/datasette
open PRs: 123 | median age 199.0d
buckets: fresh 3 | aging 7 | stale 4 | ancient 109 | quiet (no comments, old): 113

      #   age  bucket  author           title
    363  2946d  ##      kevboh           Search all apps during heroku publish
      ...
```

Release notes from merged pull requests, grouped into Added, Fixed,
Breaking changes and more by label and conventional-commit prefix. Point
it at a tag and it works out the window for you. Output pastes straight
into a release page or CHANGELOG:

```text
$ prsnoop changelog owner/repo --tag v1.2.0

## What's changed

### Added
- transform: coerce empty strings to NULL ([#805](...)) @ikatyal2110

### Fixed
- Fix for 4.2 crashing bug ([#843](...)) @simonw
```

Contribution quality gates for CI. Fetch the window, apply thresholds,
write a GitHub step summary, and exit 1 when a gate fails, so a scheduled
workflow can fail loudly when a contributor program stalls:

```bash
prsnoop ci your-username --min-prs 5 --min-merge-rate 40 --max-merge-days 7
```

Watch the terminal come alive. An ANSI dashboard that refetches every N
seconds, redraws, and rings the bell when a new pull request appears:

```bash
prsnoop watch your-username --every 60       # ctrl-c to stop
prsnoop watch your-username --once           # one frame, for demos
```

Reports without the network. Freeze a snapshot once, then re-render any
format, even the wrapped superlatives, offline and byte for byte:

```bash
prsnoop snap simonw -o august.json
prsnoop replay august.json -f markdown       # no API calls at all
prsnoop replay august.json --wrapped
```

HTML reports for wide windows include a GitHub-style contribution
calendar, one cell per day, greener means more shipped.

Score your contributor health, 0-100 with a letter grade, five weighted
pillars, and a burnout-risk flag computed from streak length and workload:

```text
$ prsnoop score simonw

  SCORE   77.3 / 100   grade B (strong)

  output          67.9  x0.30  [###################.........]
                 33 PRs, +13,607 lines, 59 issues

  impact          92.7  x0.25  [##########################..]
                 88% merge rate, 0.0d median merge
  ...
  burnout risk: low (healthy pacing across the window)
```

Unlock achievements, 62 badges across common, rare, epic, and legendary
tiers, with points and completion percentage:

```text
$ prsnoop achievements simonw

  SCORE   870 pts   31/62 unlocked (50%)

  UNLOCKED
   (*)   First Blood        common    Opened your first pull request
   (*)   Double Digits      common    Opened 10 pull requests
   (**)  Quarter Century    rare      Opened 25 pull requests
   ...
```

Forecast your pace with a least-squares fit over the daily series:

```bash
prsnoop forecast simonw                  # trajectory, PRs/week, next-30 projection
prsnoop forecast simonw --horizon 90     # longer horizon
```

Ask questions in plain English, answered locally from the snapshot with no
API key:

```text
$ prsnoop ask simonw "top language?" "how many prs?" "merge rate?"

  Q: top language?
  A: The top language is Python with 20 PRs.

  Q: how many prs?
  A: simonw opened 33 pull requests in the last 30 days (29 merged, 3 still open).
```

Watch the terminal turn into a dashboard. A full-screen curses UI with four
tabbed views, scrolling, and periodic refresh, htop for GitHub:

```bash
prsnoop tui simonw                       # 1-4 tabs, j/k scroll, r refresh, q quit
```

See the review network, render the timeline, generate a Slack digest, and
produce a one-page HTML masterpiece with score bars, an achievement wall, a
language donut, and a forecast strip:

```bash
prsnoop network simonw --format dot | dot -Tpng -o network.png
prsnoop timeline simonw
prsnoop digest simonw --format slack     # paste into a webhook
prsnoop report simonw -o report.html     # one file, no assets, opens anywhere
```

HTML reports for wide windows include a GitHub-style contribution
calendar, one cell per day, greener means more shipped.

Level up. Merges, lines, reviews, and achievement points all convert to
xp, xp maps to a level, and levels map to ranks, DRIFTER through GHOST:

```text
$ prsnoop level simonw

  LEVEL  19   RECRUIT
  XP        8,075

  next rank APPRENTICE at level 20
  progress  #                    8%
```

Contributor dna: a 32-character genome hashed from your stats, rendered
as a symmetric fingerprint glyph with a signature reading of your style:

```text
$ prsnoop dna simonw

  genome    089b56dae7af1de3
            e08b9dff014254da
  signature high-output · collaborative
  color     #ff7eb6
```

Responsiveness: for every PR in the window, how long it waited for a
first review and how long you took to answer it. Per-repo medians, the
slowest open waits, and a verdict on whose side the silence is on:

```text
$ prsnoop responsiveness simonw

  median time to first review : 0m
  median time to your reply   : 0m
  median total open time      : 12m

  verdict: healthy turnaround on both sides
```

Three interactive HTML generators, all real data, each a single file:
showcase, a surveillance dossier with radar chart, heatmap, force graph
and explorer; wrapped, a slide-by-slide story of your year; and battle,
an animated head-to-head versus page:

```bash
prsnoop showcase simonw -o showcase.html
prsnoop wrapped simonw --web -o wrapped.html
prsnoop battle antfu simonw -o battle.html
```

Freeze a snapshot now, diff against it later. Handy for weekly reviews,
standup prep, or proving a productive month:

```bash
prsnoop snap simonw -o august.json
prsnoop snap simonw --compare august.json
```

Check your token and rate budget, or empty the cache:

```bash
prsnoop auth
prsnoop auth --clear-cache
```

## Output formats

| Format | Flag | Use it for |
|---|---|---|
| Table | default | the terminal |
| Markdown | `-f markdown` | wikis, PR descriptions, weekly reports |
| HTML | `-f html` | a standalone page, no assets, no JS |
| CSV | `-f csv` | spreadsheets, one row per PR |
| JSON | `-f json` | scripting, everything included |
| Badge | `-f badge` | README badges, see below |

```bash
prsnoop simonw -f markdown -o report.md
prsnoop simonw -f html -o report.html
prsnoop simonw -f csv -o report.csv
prsnoop simonw -f json -o report.json
```

Example reports generated by prsnoop itself live in
[examples/](examples/): [Markdown](examples/simonw_30d.md),
[HTML](examples/simonw_30d.html), [CSV](examples/simonw_30d.csv),
[an org pulse](examples/vueuse_org_pulse.md),
[badges](examples/antfu_badges.md).

## Badges

`-f badge` writes four flat-square SVG badges, pull requests, merged,
merge rate, and longest streak, as Markdown data URIs. These four are real
prsnoop output, pasted unchanged:

![prs](data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHdpZHRoPScxMjAnIGhlaWdodD0nMjAnIHJvbGU9J2ltZycgYXJpYS1sYWJlbD0ncHJzbm9vcGVkIFBSczogNDInPjx0aXRsZT5wcnNub29wZWQgUFJzOiA0MjwvdGl0bGU+PHJlY3Qgd2lkdGg9Jzk1JyBoZWlnaHQ9JzIwJyBmaWxsPScjMjQyOTJlJy8+PHJlY3QgeD0nOTUnIHdpZHRoPScyNScgaGVpZ2h0PScyMCcgZmlsbD0nIzY1NmQ3NicvPjxnIGZpbGw9JyNmZmYnIHRleHQtYW5jaG9yPSdtaWRkbGUnIGZvbnQtZmFtaWx5PSdWZXJkYW5hLEdlbmV2YSxEZWphVnUgU2FucyxzYW5zLXNlcmlmJyBmb250LXNpemU9JzExJz48dGV4dCB4PSc0NycgeT0nMTUnPnByc25vb3BlZCBQUnM8L3RleHQ+PHRleHQgeD0nMTA3JyB5PScxNSc+NDI8L3RleHQ+PC9nPjwvc3ZnPg==)
![merged](data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHdpZHRoPScxMDEnIGhlaWdodD0nMjAnIHJvbGU9J2ltZycgYXJpYS1sYWJlbD0nbWVyZ2VkIFBSczogMzcnPjx0aXRsZT5tZXJnZWQgUFJzOiAzNzwvdGl0bGU+PHJlY3Qgd2lkdGg9Jzc2JyBoZWlnaHQ9JzIwJyBmaWxsPScjMjQyOTJlJy8+PHJlY3QgeD0nNzYnIHdpZHRoPScyNScgaGVpZ2h0PScyMCcgZmlsbD0nIzJlYTA0MycvPjxnIGZpbGw9JyNmZmYnIHRleHQtYW5jaG9yPSdtaWRkbGUnIGZvbnQtZmFtaWx5PSdWZXJkYW5hLEdlbmV2YSxEZWphVnUgU2FucyxzYW5zLXNlcmlmJyBmb250LXNpemU9JzExJz48dGV4dCB4PSczOCcgeT0nMTUnPm1lcmdlZCBQUnM8L3RleHQ+PHRleHQgeD0nODgnIHk9JzE1Jz4zNzwvdGV4dD48L2c+PC9zdmc+)
![rate](data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHdpZHRoPScxMDgnIGhlaWdodD0nMjAnIHJvbGU9J2ltZycgYXJpYS1sYWJlbD0nbWVyZ2UgcmF0ZTogODglJz48dGl0bGU+bWVyZ2UgcmF0ZTogODglPC90aXRsZT48cmVjdCB3aWR0aD0nNzYnIGhlaWdodD0nMjAnIGZpbGw9JyMyNDI5MmUnLz48cmVjdCB4PSc3Nicgd2lkdGg9JzMyJyBoZWlnaHQ9JzIwJyBmaWxsPScjZDI5OTIyJy8+PGcgZmlsbD0nI2ZmZicgdGV4dC1hbmNob3I9J21pZGRsZScgZm9udC1mYW1pbHk9J1ZlcmRhbmEsR2VuZXZhLERlamFWdSBTYW5zLHNhbnMtc2VyaWYnIGZvbnQtc2l6ZT0nMTEnPjx0ZXh0IHg9JzM4JyB5PScxNSc+bWVyZ2UgcmF0ZTwvdGV4dD48dGV4dCB4PSc5MicgeT0nMTUnPjg4JTwvdGV4dD48L2c+PC9zdmc+)
![streak](data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHdpZHRoPScxMjYnIGhlaWdodD0nMjAnIHJvbGU9J2ltZycgYXJpYS1sYWJlbD0nbG9uZ2VzdCBzdHJlYWs6IDZkJz48dGl0bGU+bG9uZ2VzdCBzdHJlYWs6IDZkPC90aXRsZT48cmVjdCB3aWR0aD0nMTAxJyBoZWlnaHQ9JzIwJyBmaWxsPScjMjQyOTJlJy8+PHJlY3QgeD0nMTAxJyB3aWR0aD0nMjUnIGhlaWdodD0nMjAnIGZpbGw9JyNkMjk5MjInLz48ZyBmaWxsPScjZmZmJyB0ZXh0LWFuY2hvcj0nbWlkZGxlJyBmb250LWZhbWlseT0nVmVyZGFuYSxHZW5ldmEsRGVqYVZ1IFNhbnMsc2Fucy1zZXJpZicgZm9udC1zaXplPScxMSc+PHRleHQgeD0nNTAnIHk9JzE1Jz5sb25nZXN0IHN0cmVhazwvdGV4dD48dGV4dCB4PScxMTMnIHk9JzE1Jz42ZDwvdGV4dD48L2c+PC9zdmc+)

Generated locally, embedded directly in the Markdown. No badge service to
depend on, no rate limit to hit, no network call when someone loads your
README. Paste once, they render forever.

Regenerate yours with:

```bash
prsnoop your-username --days 30 -f badge -o badges.md
```

## GitHub Actions

A reusable composite action ships in this repo. One step in any workflow:

```yaml
- uses: MohammedAnasNathani/prsnoop/.github/actions/prsnoop-report@main
  with:
    user: your-username
    days: "7"
    token: ${{ secrets.GITHUB_TOKEN }}
```

It writes the report to the run summary and drops the file as an artifact.
A scheduled example ships in [`.github/workflows/weekly-report.yml`](.github/workflows/weekly-report.yml).

For hard gates instead of a report, `prsnoop ci` is one step: it writes
the step summary itself and fails the job when a gate fails.

```yaml
- run: prsnoop ci your-username --min-prs 5 --max-merge-days 7
  env:
    PRSNOOP_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Tokens and caching

prsnoop reads `PRSNOOP_TOKEN` or `GITHUB_TOKEN` from the environment.
Nothing else, nothing phoned home.

| | Without token | With token |
|---|---|---|
| Core requests | 60 per hour | 5000 per hour |
| Data | public repos | public repos |

```bash
export PRSNOOP_TOKEN=ghp_xxx          # macOS, Linux
$env:PRSNOOP_TOKEN = "ghp_xxx"        # PowerShell
```

Create a token at github.com/settings/tokens, no scopes needed for public
data. Every response is cached under `~/.cache/prsnoop` and revalidated
with ETags, so a second run of the same report costs nothing. Very active
accounts (300+ PRs in a window) skip per-PR enrichment instead of
spending hours of API budget, and the report says so.

## What it measures

| Metric | Definition |
|---|---|
| Pull requests | PRs authored in the window, split merged / open / closed |
| Merge rate | merged divided by authored |
| Merge time | created to merged, median and p90 |
| Reviews given | reviews and substantive comments on other authors' PRs |
| Issues | issues authored, with closed count |
| Lines changed | additions and deletions across your PRs |
| Active days | UTC days with any PR, issue, or review |
| Streaks | longest and current runs of consecutive active days |
| Languages | PR count by each repository's primary language |
| Top repositories | PR count per repo, ranked |
| Where work lands | per-repo merge rate and median merge time, 2+ PRs |
| PR size profile | typical size as XS / S / M / L / XL, over changed lines |

Exit codes: 0 success, 1 failed gate (`prsnoop ci` only), 2 usage error,
3 API error, 4 rate limited (set a token).

## How it compares

| Need | prsnoop | gh CLI | OpenSauced | OSS Insight |
|---|---|---|---|---|
| Time to first report | one command | write a jq pipeline | sign up, connect | browse to site |
| Merge timing percentiles | yes | manual | partial | repo focused |
| Daily activity, streaks | yes | manual | streaks only | no |
| Compare two people | yes | manual | no | no |
| Compare two time windows | yes | manual | no | no |
| README badges | built in | third party service | no | no |
| SVG stat card | built in | no | no | no |
| Open PR triage radar | yes | manual | no | no |
| Release notes from merged PRs | yes | manual | no | repo focused |
| CI quality gates | yes | no | no | no |
| Health score + burnout risk | yes | no | no | no |
| Achievements (40+ badges) | yes | no | gamified | no |
| Pace forecasting | yes | no | no | no |
| Natural-language Q&A | yes | no | copilot | no |
| Full-screen live TUI | yes | no | no | no |
| Output formats | 6 | text | web views | web views, API |
| Runs over SSH, in CI, offline | yes | yes | no | no |

- **gh CLI** lists PRs fine. Turning them into a report means writing the
  same jq pipeline every time. prsnoop is the pipeline, packaged.
- **OpenSauced** is a good funded product for organization dashboards.
  It is not something you run in a terminal over SSH.
- **OSS Insight** (PingCAP) analyzes billions of events for ecosystem
  research. It is not a personal report generator.
- **Your GitHub profile** shows counts. No rates, no timing, no document.

## Development

```bash
git clone https://github.com/MohammedAnasNathani/prsnoop && cd prsnoop
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest          # 209 tests, all offline
ruff check .    # lint
mypy            # strict typing
```

CI runs the same three steps on Windows, macOS, and Ubuntu across Python
3.10 to 3.14 on every push and pull request.

Ground rules in [CONTRIBUTING.md](CONTRIBUTING.md): zero runtime
dependencies, no network in tests, small public API, deterministic
renderers. The 23 open [issues](https://github.com/MohammedAnasNathani/prsnoop/issues)
are a good place to start.

Tagging a version (`git tag v1.2.0 && git push origin v1.2.0`) runs the
checks, builds the package, and attaches it to a GitHub release. With a
`PYPI_API_TOKEN` secret set, distributions publish to PyPI too.

## License

[MIT](LICENSE)
