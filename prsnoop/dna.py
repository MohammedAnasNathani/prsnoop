"""Contributor DNA: a deterministic visual fingerprint.

The contributor's stats are hashed into a seed that generates a symmetric
SVG glyph (identicon-style, in the dossier palette) plus a hex "genome"
readout where each byte encodes one metric. Same contributor, same window,
same DNA — a shareable identity mark.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from prsnoop.models import Activity, JsonDict


@dataclass(slots=True)
class Dna:
    """The fingerprint: genome string, seed, grid, and palette slot."""

    user: str
    genome: str          # hex readout, 16 bytes = 32 chars
    seed: bytes
    grid: list[list[int]]  # 7x7 symmetric intensity matrix 0-3
    color: str           # assigned palette slot
    signature: str       # one-line human readout

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "genome": self.genome,
            "color": self.color,
            "signature": self.signature,
            "grid": self.grid,
        }


PALETTE = ["#3dffa2", "#58a6ff", "#f0b429", "#b58cff", "#ff7eb6", "#2dd4bf"]


def build_dna(activity: Activity) -> Dna:
    """Hash the snapshot's shape into a stable fingerprint."""
    s = activity.stats
    payload = "|".join([
        activity.user,
        str(s.prs_authored), str(s.prs_merged), str(s.prs_open),
        str(s.reviews_given), str(s.issues_opened), str(s.issues_closed),
        str(s.lines_added), str(s.lines_deleted),
        str(s.active_days), str(s.longest_streak_days),
        str(s.distinct_repos), str(s.distinct_languages),
        str(s.busiest_day_count), str(round(s.merge_rate, 3)),
    ])
    digest = hashlib.sha256(payload.encode()).digest()
    genome = digest[:16].hex()

    # 7x7 symmetric grid from the first 25 bytes (mirror the left half)
    grid: list[list[int]] = []
    for row in range(7):
        line: list[int] = []
        for col in range(4):  # left half + center
            byte = digest[(row * 4 + col) % len(digest)]
            line.append(byte % 4)  # intensity 0-3
        mirrored = list(reversed(line[:3]))
        grid.append(line + mirrored)
    color = PALETTE[digest[20] % len(PALETTE)]

    # signature: dominant trait encoded as words
    traits = []
    if s.prs_merged >= 20:
        traits.append("high-output")
    if s.longest_streak_days >= 14:
        traits.append("relentless")
    if s.reviews_given >= 10:
        traits.append("collaborative")
    if s.distinct_languages >= 4:
        traits.append("polyglot")
    if s.lines_deleted > s.lines_added:
        traits.append("refiner")
    if not traits:
        traits.append("emerging")
    signature = " · ".join(traits[:3])

    return Dna(
        user=activity.user,
        genome=genome,
        seed=digest,
        grid=grid,
        color=color,
        signature=signature,
    )


def render_dna_svg(d: Dna, cell: int = 26) -> str:
    """The glyph as a standalone SVG."""
    size = 7 * cell
    rects = []
    for r, row in enumerate(d.grid):
        for c, intensity in enumerate(row):
            if intensity == 0:
                continue
            opacity = (0.25 + 0.25 * intensity) if intensity < 3 else 1.0
            rects.append(
                f'<rect x="{c * cell}" y="{r * cell}" width="{cell - 2}" '
                f'height="{cell - 2}" fill="{d.color}" opacity="{opacity:.2f}"/>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" role="img" aria-label="DNA of {d.user}">'
        f'<rect width="{size}" height="{size}" fill="none"/>'
        + "".join(rects) + "</svg>"
    )


def render_dna_table(d: Dna) -> str:
    lines = [
        f"prsnoop dna | {d.user}",
        "",
        f"  genome    {d.genome[:16]}",
        f"            {d.genome[16:]}",
        f"  signature {d.signature}",
        f"  color     {d.color}",
        "",
        "  " + "\n  ".join(
            "".join(" .:-#"[v] for v in row) for row in d.grid
        ),
    ]
    return "\n".join(lines)


def render_dna_markdown(d: Dna) -> str:
    import base64

    svg = render_dna_svg(d)
    b64 = base64.b64encode(svg.encode()).decode()
    return "\n".join([
        f"# DNA: {d.user}",
        "",
        f"![dna](data:image/svg+xml;base64,{b64})",
        "",
        f"**Genome:** `{d.genome}`",
        "",
        f"**Signature:** {d.signature}",
        "",
    ])
