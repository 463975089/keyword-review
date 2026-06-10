"""Orchestrator: scan a PR diff for forbidden keywords and submit a review."""
from __future__ import annotations

import os
import sys
from typing import Mapping

from .keywords_loader import load_rules, Rule
from .diff_parser import iter_added_lines
from .matcher import match_line
from .github_client import get_pr_files, post_review

_REQUIRED_ENV = ("GITHUB_TOKEN", "REPO", "PR_NUMBER")
_MAX_FILES = 300


def _warn(msg: str) -> None:
    print(f"[keyword-checker] WARNING: {msg}", file=sys.stderr)


def _fail(msg: str) -> None:
    print(f"[keyword-checker] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _format_comment_body(rules: list[Rule]) -> str:
    if len(rules) == 1:
        r = rules[0]
        return f"**{r.message}** (`{r.value}`)"
    lines = ["**Multiple rules triggered on this line:**"]
    for r in rules:
        lines.append(f"- {r.message} (`{r.value}`)")
    return "\n".join(lines)


def _build_comments(files: list[dict], rules: list[Rule]) -> list[dict]:
    comments: list[dict] = []
    for f in files:
        if f.get("status") == "removed":
            continue
        patch = f.get("patch")
        if not patch:
            continue
        path = f["filename"]
        for line_no, content in iter_added_lines(patch):
            hits = match_line(content, rules)
            if not hits:
                continue
            comments.append({
                "path": path,
                "line": line_no,
                "side": "RIGHT",
                "body": _format_comment_body(hits),
            })
    return comments


def _build_body(violations: int, truncated_extra: int,
                no_violation_action: str) -> tuple[str, str]:
    """Return (review_body, event)."""
    if violations == 0:
        action = no_violation_action.lower()
        if action not in ("comment", "approve"):
            _warn(f"unknown NO_VIOLATION_ACTION {no_violation_action!r}; "
                  f"defaulting to comment")
            action = "comment"
        event = "APPROVE" if action == "approve" else "COMMENT"
        body = "Keyword Checker: no violations found. ✅"
    else:
        event = "REQUEST_CHANGES"
        body = (f"Keyword Checker: found **{violations}** violation"
                f"{'s' if violations != 1 else ''} in this PR.")

    if truncated_extra > 0:
        body += (f"\n\n> ⚠️ Skipped {truncated_extra} additional file"
                 f"{'s' if truncated_extra != 1 else ''} beyond the "
                 f"{_MAX_FILES}-file limit.")
    return body, event


def main(env: Mapping[str, str] | None = None) -> int:
    env = env if env is not None else os.environ
    for key in _REQUIRED_ENV:
        if not env.get(key):
            _fail(f"missing required environment variable {key}")

    token = env["GITHUB_TOKEN"]
    repo = env["REPO"]
    try:
        pr_number = int(env["PR_NUMBER"])
    except (TypeError, ValueError):
        _fail(f"PR_NUMBER must be an integer, got {env.get('PR_NUMBER')!r}")
    keywords_path = env.get("KEYWORDS_PATH", ".github/keywords.yml")
    no_violation_action = env.get("NO_VIOLATION_ACTION", "comment")

    rules = load_rules(keywords_path)
    files, truncated_extra = get_pr_files(repo, pr_number, token,
                                          max_files=_MAX_FILES)
    comments = _build_comments(files, rules)
    body, event = _build_body(len(comments), truncated_extra, no_violation_action)

    post_review(repo, pr_number, token,
                comments=comments, body=body, event=event)

    print(f"[keyword-checker] {len(comments)} violation(s) reported; "
          f"event={event}; scanned={len(files)} file(s); "
          f"skipped_extra={truncated_extra}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
