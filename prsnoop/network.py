"""Review network: who reviews whom, and where work flows.

Builds a directed graph from PR authors to the repos they touch and from
reviews given per repo, then renders it as an ASCII graph plus a Graphviz
DOT export ready for `dot -Tpng`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from prsnoop.models import Activity, JsonDict


@dataclass(slots=True)
class NetworkNode:
    """A node in the collaboration graph (a repo or a collaborator)."""

    name: str
    kind: str            # repo | collaborator
    weight: int          # interactions through this node

    def to_dict(self) -> JsonDict:
        return {"name": self.name, "kind": self.kind, "weight": self.weight}


@dataclass(slots=True)
class ReviewNetwork:
    """The PR/review flow graph for one contributor."""

    user: str
    repo_nodes: list[NetworkNode] = field(default_factory=list)
    edges: list[tuple[str, str, int]] = field(default_factory=list)  # user->repo count
    review_edges: list[tuple[str, int]] = field(default_factory=list)  # repo->reviews
    languages: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "repos": [n.to_dict() for n in self.repo_nodes],
            "edges": [{"from": a, "to": b, "weight": w} for a, b, w in self.edges],
            "review_edges": [{"repo": r, "reviews": n} for r, n in self.review_edges],
            "languages": [
                {"language": lang, "prs": n} for lang, n in self.languages
            ],
        }


def build_network(activity: Activity) -> ReviewNetwork:
    s = activity.stats
    repo_counts: dict[str, int] = {}
    for p in activity.prs:
        repo_counts[p.repo] = repo_counts.get(p.repo, 0) + 1
    repo_nodes = [
        NetworkNode(name=r, kind="repo", weight=n)
        for r, n in sorted(repo_counts.items(), key=lambda kv: -kv[1])[:15]
    ]
    edges = [(activity.user, r, repo_counts[r]) for r, _ in
             [(n.name, n.weight) for n in repo_nodes]]
    review_by_repo: dict[str, int] = {}
    for r in activity.reviews:
        review_by_repo[r.repo] = review_by_repo.get(r.repo, 0) + 1
    review_edges = sorted(review_by_repo.items(), key=lambda kv: -kv[1])[:10]
    return ReviewNetwork(
        user=activity.user,
        repo_nodes=repo_nodes,
        edges=edges,
        review_edges=review_edges,
        languages=s.languages[:10],
    )


def render_network_table(net: ReviewNetwork) -> str:
    lines = [f"prsnoop network | {net.user}", ""]
    if not net.repo_nodes:
        lines.append("  no activity in this window")
        return "\n".join(lines)
    peak = net.repo_nodes[0].weight or 1
    lines.append("  work flow (you -> repos)")
    for node in net.repo_nodes:
        bar = "#" * max(1, int(node.weight / peak * 24))
        lines.append(f"  {node.name:<28} {bar} {node.weight}")
    if net.review_edges:
        lines += ["", "  review flow (reviews given per repo)"]
        for repo, n in net.review_edges:
            lines.append(f"  {repo:<28} {'~' * max(1, min(n, 24))} {n}")
    if net.languages:
        tops = ", ".join(f"{lang} ({n})" for lang, n in net.languages[:5])
        lines += ["", f"  languages: {tops}"]
    return "\n".join(lines)


def render_dot(net: ReviewNetwork) -> str:
    """Graphviz DOT for `dot -Tpng network.png`."""
    lines = [
        "digraph prsnoop {",
        "  rankdir=LR;",
        "  bgcolor=\"transparent\";",
        f"  \"{net.user}\" [shape=box, style=filled, fillcolor=\"#58a6ff\"];",
    ]
    for node in net.repo_nodes:
        top_weight = net.repo_nodes[0].weight if net.repo_nodes else 1
        fill = "#3fb950" if node.weight >= top_weight else "#30363d"
        lines.append(
            f"  \"{node.name}\" [shape=ellipse, style=filled, fillcolor=\"{fill}\", "
            f"fontcolor=\"white\"];"
        )
    for a, b, w in net.edges:
        lines.append(f"  \"{a}\" -> \"{b}\" [weight={w}, penwidth={max(1, min(w, 6))}];")
    for repo, n in net.review_edges:
        lines.append(
            f"  \"{repo}\" -> \"{net.user}\" [style=dashed, color=\"#d29922\", "
            f"label=\"{n} reviews\"];"
        )
    lines.append("}")
    return "\n".join(lines) + "\n"
