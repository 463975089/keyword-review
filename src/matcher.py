"""Match a single line of content against a list of Rule objects."""
from __future__ import annotations

from .keywords_loader import Rule


def match_line(line: str, rules: list[Rule]) -> list[Rule]:
    """Return the subset of `rules` triggered by `line`, in original order."""
    if not line:
        return []
    hits: list[Rule] = []
    for rule in rules:
        if rule.kind == "string":
            if rule.value in line:
                hits.append(rule)
        elif rule.kind == "regex":
            if rule.compiled is None:
                raise ValueError(
                    f"regex Rule with value={rule.value!r} has compiled=None; "
                    "construct Rule via load_rules() or pass a compiled pattern"
                )
            if rule.compiled.search(line):
                hits.append(rule)
    return hits
