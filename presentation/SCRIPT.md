# prsnoop · speaker script

Final review, 16 slides. Roughly **45 seconds a slide**, so about **12 minutes** total including the live demo and the closing clip.

Read it out loud once to find your own rhythm. The timings are targets, not rules. Where it says *pause*, actually pause, it lands better than filling the silence.

Anything in `code font` is a command or a flag, say it however feels natural.

---

## 1 · Cover

**~40s · 101 words**

Good morning. This is prsnoop. You give it a GitHub username, and it tells you what that person actually did with their pull requests. Not just how many. How fast they merged, how big the patches were, whether they are quietly burning out, and how they stack up against someone else. It runs in a terminal, it has no dependencies, and every number in this deck came from running it for real. No mockups anywhere. I will walk you through the problem we started with, the design, every version from 1.0 to 2.3, and then we run the whole thing live.

---

## 2 · Agenda

**~48s · 120 words**

Quick map of where we are going. The first two slides are context: what the problem actually is, and why the tools that already exist do not solve it. The middle chunk is the product. How it is built, and how it grew across twelve releases. Then the last third is proof. We run every command live, we show you the test suite and the CI pipeline, and we show you what actually shipped. Four of us built this over the semester. You will meet us properly on slide fourteen.

If you want to jump around, the tab bar along the top goes straight to any slide, so you do not have to sit through anything you have already seen.

---

## 3 · Problem

**~59s · 148 words**

Here is the thing that started all of this. Your GitHub profile shows a wall of green squares. Everybody reads that as "this person is productive". But those squares answer none of the questions that actually matter. Did anything I wrote get merged? Am I getting faster or slower? Am I the one who is quietly burning out? And how do I compare, honestly, to somebody else? The heatmap on the right is exactly what GitHub shows everybody. It counts activity. It does not tell you whether any of it landed.

So we looked at what already exists. The official `gh` CLI lists pull requests, and that is it, no analysis. OpenSauced is a dashboard, but you need an account, and it never runs in your terminal or in CI. OSS Insight looks at whole ecosystems, not at one person. So we built the thing that was missing.

---

## 4 · What it is, and how it works

**~44s · 111 words**

One username in, one report out. No account, no server, nothing leaves your machine.

Under the hood it is a pipeline. Fetch, then enrich each pull request, then normalise all of it into a single snapshot object. That snapshot is the whole design. Every renderer reads from it and nothing else. Seven core modules, and the snapshot is the seam between them.

That is why the numbers never disagree with each other. If the table says one merge rate, the HTML report says the same, the JSON says the same, the badge says the same. They are not four calculations that happen to agree. They are four views of one object.

---

## 5 · Engineering rules

**~54s · 136 words**

Reliability here was a design decision, not an afterthought.

Tokens come from the environment only. Never written to disk, never logged, never pasted into a report. Rate limits are handled properly: a secondary limit gets retried with backoff, and if we genuinely run out, it fails fast with exit code four instead of hanging your terminal. Every request carries an ETag, so running the same report twice costs no quota at all.

The exit codes are a contract. Zero is fine, two is a usage error, three is an API error, four is rate limiting. Your CI job can branch on that without parsing a single line of text.

One more thing I like. Past three hundred pull requests, it marks the line totals partial. It would rather admit the limit than print a wrong number.

---

## 6 · Version 1

**~47s · 117 words**

Version one was about making the core solid, and nothing else.

1.0.0 shipped the piece everything else depends on: a REST client with zero dependencies and ETag caching. Forty seven tests. Then 1.1 added the timing analytics, so percentiles, streaks, language mix. 1.2 brought badge generation and the reusable GitHub Action. 1.3 added org-level reports and window over window trends.

1.4 gave us repo maintainer mode and the `me` command, so you never type your own name. 1.5 is where wrapped landed, plus the live dashboard. 1.6 rounded it out with the SVG card, the radar triage, and the CI gates.

Seven releases, one continuous line. Nothing earlier was ever broken to make room for something later.

---

## 7 · Version 2

**~42s · 104 words**

Version two changed what the tool was for.

Version one told you what you did. Version two tells you what it means.

2.0 added the judgement layer: the health score with its burnout flag, achievements, forecast, and a local question answering command. 2.1 went to the browser, with showcase, battle, and the wrapped story mode. 2.1.1 was the identity pass, so every generated page finally looked like it came from the same product instead of four different ones.

2.2 added levels and the DNA fingerprint. And 2.3 added responsiveness, which reads the real review timeline and tells you whose side the silence is on.

---

## 8 · Formats and scoring

**~48s · 119 words**

Two ideas share this slide.

First, one snapshot becomes seven formats. Table, markdown, HTML with a heatmap, CSV, JSON, YAML, and badges as inline SVG. Same data, seven renderers, zero drift between them.

Second, the numbers get meaning. Zero to a hundred on a weighted health score. This developer lands at seventy one point two, which is a B. Five pillars sit behind that. Output is strong. Impact is the highest of the five. Consistency is solid. Collaboration is thirteen point three, and that is the honest weak spot. It is not a bug. The data says this person gives no reviews.

And rhythm sits at forty. The tool is not flattering anybody. It is just reading the record.

---

## 9 · Wrapped, the web surfaces, and the analytics

**~53s · 132 words**

This is the slide I would show someone who thinks it is just a statistics tool.

On the left, wrapped. It is the Spotify year in review treatment, applied to pull requests. It runs as a table, markdown, JSON, or a swipeable web story, all from the same numbers. Then the surfaces. Showcase builds a whole interactive web app in a single file. Battle does head to head. Card makes a stat card you can drop into a README. Every one of them is one file with no external requests, so you can email it to somebody and it just opens.

On the right, the analytics. Responsiveness reads the real review timeline. Forecast fits a line and projects your pace. Ask answers plain English questions locally, no API key, no model call.

---

## 10 · The command surface

**~41s · 103 words**

Thirty subcommands, one grammar. And please do not read all thirty, I will not.

The point is the groups. Scoring, progression, the web surfaces, team and repo reports, and the operational ones.

What I actually want you to notice is the strip at the bottom. Every single subcommand takes the same window flags and the same format flags. So days, last month, since, until, the format flag, they work everywhere. Learning one command teaches you the whole tool.

There are two more entry points beyond the thirty. The bare `prsnoop user` report, and `auth`, which tells you your token and rate limit status.

---

## 11 · Live demo

**~41s · 102 words**

This is the part where I stop talking.

Press PLAY ALL and it types through every command in order, on real data. If it hesitates for a second, that is the first network fetch. After that everything is cached and it comes back instantly. That first fetch is the only slow moment in the whole demo, so please do not read anything into it.

If you want to stop me on something specific, the group buttons run just that area. Core and formats, the version two analytics, team and repo, the web surfaces, or the ops commands. Otherwise, just watch it go.

---

## 12 · Quality and shipping

**~45s · 112 words**

None of this was pretty before it was correct.

Two hundred and seventy seven tests, across thirteen files, and all of them run offline. The HTTP layer is faked, so the suite proves the statistics and the rendering without ever touching the network. It started at forty seven tests back in version one.

The CI matrix fans out across fifteen runners. Ubuntu, macOS and Windows, against Python 3.10 through 3.14, and every one of them runs pytest, ruff, and mypy in strict mode. Three more workflows handle Pages, releases, and the weekly report.

It is pure Python with no dependencies, so it installs anywhere. Ten tagged releases so far, each with built distributions.

---

## 13 · What actually shipped

**~46s · 114 words**

Here is what actually shipped. Thirty subcommands, two hundred and sixty tests, twelve releases, seven formats, sixty two achievements, and zero dependencies.

The part I am proudest of is the self report. That block in the middle is prsnoop describing its own repository. Ten pull requests opened, nine merged, two active authors, and those are real pull request titles from this project. We did not write a mockup for this deck. We ran the tool on our own repo.

Then the comparison table. I will be straight about the gap, because you would find it anyway. We are not on PyPI yet, and there is no editor plugin. Those are the next two things.

---

## 14 · The team

**~56s · 141 words**

Four people built this, and I want to give each of them a real minute.

Sofiya built the fetch pipeline and the statistics underneath it. The percentiles, the activity bucketing, the streak maths.

Haadiya owns quality. She took the test suite from forty seven tests to two hundred and sixty, built the fake HTTP layer, and kept ruff and mypy clean across every single release.

Naahid built everything you look at. The renderers, the hand written SVG badges, the showcase app, the battle page, the wrapped story mode.

And Anas designed the snapshot model and the command grammar, wrote the version two analytics, and cut every release from 1.2.0 up to 2.3.0.

Forty eight commits, four contributors. Every change landed the same way: an issue, a branch, a pull request, a review, a green check, then a merge and a tag.

---

## 15 · Thank you

**~52s · 129 words**

That is the project.

One command to install it. It runs on Python 3.10 to 3.14, on macOS, Linux and Windows. The repository is at github dot com slash MohammedAnasNathani slash prsnoop, and there are links on screen for the live page and the releases.

Everything in this deck is reproducible from a snapshot, so if you want to see any command again, we can run it right now.

Open issues go from good first issue all the way up to advanced, so it is a genuinely open project.

If you take one thing away from this, take this: it is small, it is tested, and it is usable today. Nothing here is a demo that falls apart the moment you point it at a different repository.

Thank you.

---

## 16 · Closing clip

**~18s · 45 words**

Press PLAY THE ENDING. Let the clip run all the way through without talking over it, then take questions.

If you are presenting from a phone in landscape and the clip will not start, tap it once. Browsers block autoplay until you touch the page.

---

## Practical notes

**Before you start.** Warm the cache. Open the terminal and run `bash presentation/warm.sh`. It takes about twenty seconds and after that every command answers instantly for the rest of the session. While it works you will see a counter ticking up, like `fetching pull requests 40/84`. That counter is your friend. It means the tool is talking to GitHub, not stuck.

**If you forget to warm it,** a fresh user costs about twenty seconds. That is not us being slow. GitHub answers one request per pull request to get the diff sizes, and each round trip is roughly half a second, so a user with eighty pull requests is about eighty of them. You cannot make that faster, you can only pay it once, which is exactly what warming the cache does.

**If a number looks different live.** The deck's demo blocks were captured from a snapshot, and the GitHub API keeps moving. If the live run shows slightly different totals, say so. "This is live data, so it has moved a little since we captured the deck." That is a stronger answer than pretending it matches.

**Timing.** If you are running long, cut slide 5 and slide 12 down to two sentences each. They are the two most compressible. Do not cut slide 14, that one is about people.

**Questions.** If something needs a live answer, `prsnoop ask <username> "your question"` handles a lot of the obvious ones without a network call.
