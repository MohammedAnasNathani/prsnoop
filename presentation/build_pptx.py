"""Build presentation/prsnoop_rosp.pptx : 10-slide ROSP deck mirroring index.html."""
from __future__ import annotations

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Pt

INK = RGBColor(0x0A, 0x0A, 0x0C)
PAPER = RGBColor(0xFB, 0xFB, 0xFA)
DIM = RGBColor(0x5D, 0x5D, 0x64)
FAINT = RGBColor(0x9A, 0x9A, 0xA2)
GREEN = RGBColor(0x15, 0x80, 0x3D)
GREEN_BG = RGBColor(0xE7, 0xF4, 0xEC)
LINE = RGBColor(0xE2, 0xE2, 0xDD)

prs = Presentation()
prs.slide_width = Emu(12192000)
prs.slide_height = Emu(6858000)
BLANK = prs.slide_layouts[6]


def _bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _box(slide, left, top, width, height):
    return slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))


def _para(tf, text, size, bold=False, color=INK, font="Calibri", align=None, space_after=6):
    p = tf.add_paragraph()
    p.space_after = Pt(space_after)
    if align is not None:
        p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    return p


def slide_head(slide, kicker, title_lines, sub=None):
    _box(slide, 685800, 274320, 10832400, 457200).text_frame.word_wrap = True
    tf = slide.shapes[-1].text_frame
    tf.word_wrap = True
    _para(tf, kicker.upper(), 12, color=FAINT, font="Consolas")
    tb = _box(slide, 685800, 914400, 10832400, 1371600)
    tf = tb.text_frame
    tf.word_wrap = True
    for j, line in enumerate(title_lines):
        _para(tf, line, 32, bold=True, space_after=2)
    if sub:
        tb = _box(slide, 685800, 2450000, 10832400, 800000)
        tf = tb.text_frame
        tf.word_wrap = True
        _para(tf, sub, 15, color=DIM)
    return 3400000


def bullets(slide, top, items, size=16):
    tb = _box(slide, 685800, top, 10832400, 3000000)
    tf = tb.text_frame
    tf.word_wrap = True
    for head, body in items:
        p = tf.add_paragraph()
        p.space_after = Pt(8)
        r = p.add_run()
        r.text = head + "  "
        r.font.size = Pt(size)
        r.font.bold = True
        r.font.color.rgb = GREEN
        r.font.name = "Consolas"
        r2 = p.add_run()
        r2.text = body
        r2.font.size = Pt(size)
        r2.font.name = "Calibri"
        r2.font.color.rgb = INK


def add_table(slide, top, headers, rows, widths, size=12, highlight_last=False):
    table_shape = slide.shapes.add_table(len(rows) + 1, len(headers), Emu(685800), Emu(top),
                                         Emu(sum(widths)), Emu(400000))
    table = table_shape.table
    for j, w in enumerate(widths):
        table.columns[j].width = Emu(w)
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(size)
                r.font.bold = True
                r.font.color.rgb = FAINT
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = table.cell(i, j)
            cell.text = val
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(size)
                    r.font.color.rgb = INK
            if highlight_last and i == len(rows):
                cell.fill.solid()
                cell.fill.fore_color.rgb = GREEN_BG


def build() -> None:
    # 1 · title
    s = prs.slides.add_slide(BLANK)
    _bg(s, INK)
    tb = _box(s, 685800, 1200000, 10832400, 900000)
    tf = tb.text_frame
    tf.word_wrap = True
    _para(tf, "prsnoop_", 54, bold=True, color=PAPER, font="Consolas")
    tb = _box(s, 685800, 2300000, 10832400, 1400000)
    tf = tb.text_frame
    tf.word_wrap = True
    _para(tf, "what did your pull requests actually do?", 30, bold=True, color=PAPER)
    tb = _box(s, 685800, 3800000, 10832400, 1200000)
    tf = tb.text_frame
    tf.word_wrap = True
    _para(tf, "Pull-request analytics from the command line. ROSP internal project, OSS Lab.",
          16, color=RGBColor(0xB9, 0xB9, 0xC0))
    _para(tf, "v1.3.0 released  ·  96 tests passing  ·  0 dependencies  ·  MIT", 14,
          color=GREEN, font="Consolas")
    _para(tf, "github.com/MohammedAnasNathani/prsnoop", 13, color=RGBColor(0xB9, 0xB9, 0xC0),
          font="Consolas")

    # 2 · research
    s = prs.slides.add_slide(BLANK)
    top = slide_head(s, "02 · initial research", ["We went looking for the tool.",
                                                  "It did not exist."])
    bullets(s, top, [
        ("F-1 · CLI gap is empty:", "no maintained tool for personal PR analytics (~13-star hobby repos)."),
        ("F-2 · Dashboards are crowded:", "funded web apps; nothing runs over SSH, in CI, or cron."),
        ("F-3 · gh CLI stops halfway:", "official CLI (46k stars) lists PRs; reports need hand-built jq pipelines."),
    ])

    # 3 · problem
    s = prs.slides.add_slide(BLANK)
    top = slide_head(s, "03 · problem statement", ["The profile page counts green squares.",
                                                   "It answers nothing that matters."])
    bullets(s, top, [
        ("Q1", "What share of my pull requests actually merged?"),
        ("Q2", "How long do maintainers take to merge my work?"),
        ("Q3", "Which projects and languages am I invested in?"),
        ("Q4", "What does last month look like as a document I can send?"),
    ])

    # 4 · field data
    s = prs.slides.add_slide(BLANK)
    top = slide_head(s, "04 · field data · public numbers, sep 2026",
                     ["Everyone else built a website.", "Nobody packaged the pipeline."],
                     "Stars measure the web-dashboard crowd. The scriptable personal-report column has one entry.")
    bullets(s, top, [
        ("gh CLI : 46,204 stars:", "lists PRs, zero analytics (cli/cli)."),
        ("OSS Insight : 2,505 stars:", "ecosystem research, not personal reports (pingcap/ossinsight)."),
        ("OpenSauced v1 : 948 stars:", "dashboards needing signup + hosting (open-sauced/open-sauced)."),
        ("prsnoop : new:", "occupies the empty CLI gap: one command, five formats."),
    ])

    # 5 · technical approach
    s = prs.slides.add_slide(BLANK)
    top = slide_head(s, "05 · technical approach",
                     ["Stdlib only: the import tree is already installed."])
    bullets(s, top, [
        ("github.py:", "urllib client, token auth, ETag cache (304 = free)."),
        ("fetch.py:", "search API, per-PR enrichment, 300-PR budget cap."),
        ("stats.py:", "merge rates, median + p90, streaks, language mix."),
        ("models.py + render.py + badge.py:", "dataclasses; 5 pure-function renderers; hand-built SVG badges."),
        ("Ground rules:", "0 runtime deps · no network in tests · deterministic output."),
    ])

    # 6 · flow
    s = prs.slides.add_slide(BLANK)
    top = slide_head(s, "06 · application flow", ["One command in. A document out."])
    bullets(s, top, [
        ("$ prsnoop user --days 30", "flags: --org, --since/--until, --no-reviews, -f, -o."),
        ("client -> fetcher -> stats:", "REST + cache -> search + enrich -> rates, p90, streaks."),
        ("render:", "table · markdown · html · csv · json in one pure function each."),
        ("Force multipliers:", "compare A vs B · snap --compare · --format badge · composite Action · org pulse."),
    ])

    # 7 · results
    s = prs.slides.add_slide(BLANK)
    top = slide_head(s, "07 · results · everything below was actually run",
                     ["Shipped, tested, released. Twice."])
    bullets(s, top, [
        ("96 tests", "passing, fully offline (fakes + fixtures, no network)."),
        ("15 CI jobs", "green: Windows/macOS/Ubuntu x Python 3.10-3.14, plus ruff + mypy strict."),
        ("2 releases", "v1.2.0 and v1.3.0 shipped with built distributions attached."),
        ("Live demo", "public developer, 30 days: 39 PRs, 87% merged, +16k lines."),
        ("Plus", "23 laddered issues, live landing page, reusable GitHub Action."),
    ])

    # 8 · literature review
    s = prs.slides.add_slide(BLANK)
    top = slide_head(s, "08 · literature review", ["What exists, and where each one stops."])
    add_table(s, top,
              ["Tool", "Approach", "Limitation (the gap)"],
              [["gh CLI (46k stars)", "Official CLI + jq/GraphQL scripting",
                "No analytics; every report hand-built"],
               ["OpenSauced (funded)", "Web dashboards + workspaces",
                "Signup/hosting; no terminal, CI, or cron"],
               ["OSS Insight (PingCAP)", "Ecosystem-scale event analytics",
                "Repo research, not personal reports"],
               ["prsnoop (this work)", "Zero-dep CLI, five report formats",
                "New; PyPI/plugins are roadmap"]],
              [2800000, 4200000, 4500000], highlight_last=True)

    # 9 · team
    s = prs.slides.add_slide(BLANK)
    top = slide_head(s, "09 · team contribution  [replace member names before presenting]",
                     ["Four lanes. One main branch."])
    add_table(s, top,
              ["Member", "Lane", "Delivered"],
              [["Member 1", "CLI + packaging", "Arg parsing, exit codes, wheel/sdist, releases"],
               ["Member 2", "Fetch + stats", "REST client, cache, percentiles + streaks"],
               ["Member 3", "Renderers + Action", "5 formats, badges, compare, CI Action"],
               ["Member 4", "Quality + web", "96 tests, lint + types, 15-job CI, landing page"]],
              [2500000, 3000000, 6000000])

    # 10 · thank you
    s = prs.slides.add_slide(BLANK)
    _bg(s, INK)
    tb = _box(s, 685800, 1800000, 10832400, 1500000)
    tf = tb.text_frame
    tf.word_wrap = True
    _para(tf, "thank you.", 54, bold=True, color=PAPER)
    tb = _box(s, 685800, 3400000, 10832400, 1800000)
    tf = tb.text_frame
    tf.word_wrap = True
    _para(tf, "prsnoop is MIT-licensed and open for contributions : 23 issues waiting.",
          16, color=RGBColor(0xB9, 0xB9, 0xC0))
    _para(tf, "github.com/MohammedAnasNathani/prsnoop", 15, color=PAPER, font="Consolas")
    _para(tf, "pip install prsnoop", 15, color=GREEN, font="Consolas", bold=True)


if __name__ == "__main__":
    build()
    prs.save("presentation/prsnoop_rosp.pptx")
    print("saved presentation/prsnoop_rosp.pptx with", len(prs.slides._sldIdLst), "slides")
