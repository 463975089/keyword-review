"""Minimal GitHub REST wrapper used by the keyword-checker action."""
from __future__ import annotations

import requests

GITHUB_API = "https://api.github.com"
_PER_PAGE = 100


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_pr_files(repo: str, pr_number: int, token: str,
                 *, max_files: int = 300) -> tuple[list[dict], int]:
    """Return (files, truncated_extra).

    Paginates until the next page is short (<per_page) or we hit `max_files`.
    `truncated_extra` is the number of additional files visible on a peek page
    past the cap; 0 if we collected every file.
    """
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files"
    files: list[dict] = []
    page = 1
    while True:
        resp = requests.get(url, params={"per_page": _PER_PAGE, "page": page},
                            headers=_headers(token), timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        files.extend(batch)
        if len(files) >= max_files:
            files = files[:max_files]
            # Peek one more page to report how many we knowingly skipped.
            resp = requests.get(url,
                                params={"per_page": _PER_PAGE, "page": page + 1},
                                headers=_headers(token), timeout=30)
            resp.raise_for_status()
            extra = resp.json()
            return files, len(extra)
        if len(batch) < _PER_PAGE:
            return files, 0
        page += 1


def post_review(repo: str, pr_number: int, token: str,
                *, comments: list[dict], body: str, event: str) -> dict:
    """Submit a single review with inline comments.

    `event` must be one of "APPROVE", "REQUEST_CHANGES", "COMMENT".
    `comments` items are dicts with keys: path, line, side, body
    (and optionally start_line/start_side for multi-line).
    """
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews"
    payload = {"body": body, "event": event, "comments": comments}
    resp = requests.post(url, json=payload, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()
