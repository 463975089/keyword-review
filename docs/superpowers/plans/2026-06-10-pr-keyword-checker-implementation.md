# PR Keyword Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Actions composite action that scans PR diffs for forbidden keywords (hard-coded passwords, API keys, TODOs, etc.) and posts inline review comments — similar to GitHub Copilot Code Review.

**Architecture:** A Python orchestrator script driven by a composite `action.yml`. The orchestrator loads `keywords.yml`, calls the GitHub PR Files API, parses each unified-diff `patch` to extract added lines with their new-file line numbers, matches each line against string/regex rules, and submits a single PR review containing all violations as inline comments. Concerns are split into focused submodules — `keywords_loader`, `diff_parser`, `matcher`, `github_client` — with `check_keywords.py` as the orchestrator. The repo at `/home/action/` IS the action repo (`keyword-checker`).

**Tech Stack:** Python 3.10+, PyYAML for config parsing, `requests` for GitHub API calls, `pytest` + `unittest.mock` for tests, GitHub Actions composite action.

---

## Key Design Decisions

- **Modern review API:** Use `line` + `side: "RIGHT"` (not deprecated `position`) when submitting inline comments. We only annotate added lines, so `side` is always `"RIGHT"`.
- **Single review submission:** All violations across all files are sent in one `POST /reviews` call. Event is `REQUEST_CHANGES` if any violation exists, otherwise `COMMENT` (default) or `APPROVE` (configurable).
- **Pagination cap:** PR Files endpoint returns up to 100 per page. We fetch up to 3 pages (300 files). If a 4th page exists, we add a notice line to the review body listing the skipped count.
- **Same-line merge:** When multiple rules trigger on one line, we emit a single comment whose body lists every message as bullet points.
- **Failure modes (per spec):**
  - Missing `keywords.yml` → warning to stderr, exit 0 (do not block the PR).
  - Invalid regex rule → warning to stderr, skip that rule only, continue.
  - GitHub API failure → raise, exit non-zero (PR check turns red).
- **No DinD requirement:** Composite action runs Python directly on the self-hosted runner.

---

## File Structure

Files to create (all paths relative to repo root `/home/action/`):

| Path | Responsibility |
|------|----------------|
| `action.yml` | Composite action definition: install deps, invoke script. |
| `requirements.txt` | Runtime deps: `pyyaml`, `requests`. |
| `requirements-dev.txt` | Test deps: includes runtime + `pytest`. |
| `pytest.ini` | Pytest configuration (testpaths, rootdir tweaks). |
| `.gitignore` | Ignore `__pycache__`, `.pytest_cache`, `*.pyc`. |
| `src/__init__.py` | Marks `src/` as a package (empty). |
| `src/keywords_loader.py` | Parse and validate `keywords.yml`; compile regexes; return `list[Rule]`. |
| `src/diff_parser.py` | Iterate unified-diff `patch` strings, yield `(new_line_number, content)` for each added line. |
| `src/matcher.py` | Match a content line against a list of `Rule`s; return list of triggered rules. |
| `src/github_client.py` | Thin REST wrapper: `get_pr_files`, `post_review`. Handles pagination. |
| `src/check_keywords.py` | Orchestrator entrypoint: reads env, glues modules together, exits with the right code. |
| `tests/__init__.py` | Empty. |
| `tests/conftest.py` | Shared pytest fixtures (sample rules, sample diffs). |
| `tests/test_keywords_loader.py` | Loader tests. |
| `tests/test_diff_parser.py` | Diff parser tests. |
| `tests/test_matcher.py` | Matcher tests. |
| `tests/test_github_client.py` | Client tests with `requests` mocked. |
| `tests/test_check_keywords.py` | Orchestrator integration test (everything mocked at the HTTP boundary). |
| `.github/workflows/test.yml` | CI: run pytest on push/PR. |
| `README.md` | Usage docs for consumers (business repo). |
| `examples/keywords.yml` | Sample config copy-pasteable into business repos. |

---

## Task 1: Project Skeleton

**Files:**
- Create: `/home/action/.gitignore`
- Create: `/home/action/requirements.txt`
- Create: `/home/action/requirements-dev.txt`
- Create: `/home/action/pytest.ini`
- Create: `/home/action/src/__init__.py`
- Create: `/home/action/tests/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

Write `/home/action/.gitignore`:

```gitignore
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.coverage
.venv/
venv/
*.egg-info/
```

- [ ] **Step 2: Create `requirements.txt`**

Write `/home/action/requirements.txt`:

```
pyyaml>=6.0
requests>=2.31
```

- [ ] **Step 3: Create `requirements-dev.txt`**

Write `/home/action/requirements-dev.txt`:

```
-r requirements.txt
pytest>=7.4
```

- [ ] **Step 4: Create `pytest.ini`**

Write `/home/action/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -ra --strict-markers
```

- [ ] **Step 5: Create package init files**

Write `/home/action/src/__init__.py`: (empty file, single newline)

```

```

Write `/home/action/tests/__init__.py`: (empty file, single newline)

```

```

- [ ] **Step 6: Install dev dependencies**

Run: `pip install --quiet -r /home/action/requirements-dev.txt`
Expected: silent success (or already-satisfied messages).

- [ ] **Step 7: Verify pytest discovers an empty suite**

Run: `cd /home/action && python -m pytest`
Expected: `no tests ran` (exit code 5 is acceptable here — no tests yet).

- [ ] **Step 8: Commit**

```bash
cd /home/action && git init -q 2>/dev/null || true
git add .gitignore requirements.txt requirements-dev.txt pytest.ini src/__init__.py tests/__init__.py
git commit -m "chore: project skeleton for keyword-checker action" 2>/dev/null || true
```

(If not a git repo, the `init` line creates one. The `|| true` guards against re-runs.)

---

## Task 2: Keywords Loader (TDD)

**Files:**
- Create: `/home/action/tests/test_keywords_loader.py`
- Create: `/home/action/src/keywords_loader.py`

The loader returns a list of `Rule` objects. `Rule` is a small dataclass with `kind` (`"string"` or `"regex"`), `value` (raw string), `message`, and `compiled` (a `re.Pattern` for regex rules, `None` for string rules). Invalid regexes are skipped with a warning to stderr.

- [ ] **Step 1: Write failing tests for the loader**

Write `/home/action/tests/test_keywords_loader.py`:

```python
import re
import textwrap
import pytest

from src.keywords_loader import Rule, load_rules


def write_yaml(tmp_path, body):
    path = tmp_path / "keywords.yml"
    path.write_text(textwrap.dedent(body))
    return path


def test_load_string_rule(tmp_path):
    path = write_yaml(tmp_path, """
        keywords:
          - type: string
            value: password
            message: hardcoded password
    """)
    rules = load_rules(str(path))
    assert rules == [Rule(kind="string", value="password",
                          message="hardcoded password", compiled=None)]


def test_load_regex_rule_compiles_pattern(tmp_path):
    path = write_yaml(tmp_path, """
        keywords:
          - type: regex
            value: "sk-[a-zA-Z0-9]{4,}"
            message: api key leak
    """)
    rules = load_rules(str(path))
    assert len(rules) == 1
    assert rules[0].kind == "regex"
    assert rules[0].compiled is not None
    assert rules[0].compiled.search("token sk-abcd1234 here")


def test_invalid_regex_is_skipped_with_warning(tmp_path, capsys):
    path = write_yaml(tmp_path, """
        keywords:
          - type: regex
            value: "([unclosed"
            message: should be skipped
          - type: string
            value: TODO
            message: resolve TODO
    """)
    rules = load_rules(str(path))
    assert [r.value for r in rules] == ["TODO"]
    err = capsys.readouterr().err
    assert "invalid regex" in err.lower()
    assert "([unclosed" in err


def test_missing_file_returns_empty_list_and_warns(tmp_path, capsys):
    rules = load_rules(str(tmp_path / "missing.yml"))
    assert rules == []
    err = capsys.readouterr().err
    assert "not found" in err.lower()


def test_empty_keywords_list(tmp_path):
    path = write_yaml(tmp_path, "keywords: []\n")
    assert load_rules(str(path)) == []


def test_unknown_type_is_skipped_with_warning(tmp_path, capsys):
    path = write_yaml(tmp_path, """
        keywords:
          - type: glob
            value: "*.env"
            message: env file
          - type: string
            value: TODO
            message: TODO
    """)
    rules = load_rules(str(path))
    assert [r.value for r in rules] == ["TODO"]
    assert "unknown rule type" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /home/action && python -m pytest tests/test_keywords_loader.py -v`
Expected: `ModuleNotFoundError: No module named 'src.keywords_loader'` (collection error).

- [ ] **Step 3: Implement `keywords_loader.py`**

Write `/home/action/src/keywords_loader.py`:

```python
"""Load and validate keyword rules from a YAML config file."""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

import yaml


@dataclass(frozen=True)
class Rule:
    kind: str           # "string" or "regex"
    value: str          # raw pattern as written in YAML
    message: str        # comment body when this rule triggers
    compiled: Optional[re.Pattern] = None  # compiled pattern for regex rules


def _warn(msg: str) -> None:
    print(f"[keyword-checker] WARNING: {msg}", file=sys.stderr)


def load_rules(path: str) -> list[Rule]:
    """Parse `path` and return the list of valid Rule objects.

    Returns [] (with a warning) when the file does not exist.
    Skips individual rules that are malformed or have invalid regexes.
    """
    if not os.path.isfile(path):
        _warn(f"keywords config not found at {path}; no rules will be applied")
        return []

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    raw_rules = data.get("keywords") or []
    rules: list[Rule] = []
    for entry in raw_rules:
        if not isinstance(entry, dict):
            _warn(f"skipping non-mapping rule entry: {entry!r}")
            continue
        kind = entry.get("type")
        value = entry.get("value")
        message = entry.get("message", "")
        if kind not in ("string", "regex"):
            _warn(f"unknown rule type {kind!r}; skipping entry {entry!r}")
            continue
        if not isinstance(value, str) or value == "":
            _warn(f"rule value must be a non-empty string; skipping {entry!r}")
            continue

        if kind == "regex":
            try:
                compiled = re.compile(value)
            except re.error as exc:
                _warn(f"invalid regex {value!r} ({exc}); skipping rule")
                continue
            rules.append(Rule(kind="regex", value=value, message=message,
                              compiled=compiled))
        else:
            rules.append(Rule(kind="string", value=value, message=message,
                              compiled=None))

    return rules
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /home/action && python -m pytest tests/test_keywords_loader.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/action
git add src/keywords_loader.py tests/test_keywords_loader.py
git commit -m "feat: keywords loader with regex validation and warnings"
```

---

## Task 3: Diff Parser (TDD)

**Files:**
- Create: `/home/action/tests/test_diff_parser.py`
- Create: `/home/action/src/diff_parser.py`

The parser walks a unified-diff `patch` (the string GitHub returns per file) and yields `(new_line_number, content)` tuples — one per `+` line. It updates the new-file line counter from each `@@ ... +NEW_START[,COUNT] @@` hunk header. Deletion lines (`-`) do not advance `new_line_number`; context lines (` `) and `+` lines do. The leading `+`, `-`, or ` ` is stripped from yielded content. The `+++ b/path` header line is ignored.

- [ ] **Step 1: Write failing tests**

Write `/home/action/tests/test_diff_parser.py`:

```python
import textwrap

from src.diff_parser import iter_added_lines


def test_single_hunk_single_addition():
    patch = textwrap.dedent("""\
        @@ -1,3 +1,4 @@
         context line
        +new line
         another context
         third context""")
    assert list(iter_added_lines(patch)) == [(2, "new line")]


def test_multiple_additions_with_deletions():
    patch = textwrap.dedent("""\
        @@ -10,4 +10,5 @@
         keep one
        -drop me
        +added one
        +added two
         keep two""")
    # new-file line numbering: keep one=10, added one=11, added two=12, keep two=13
    assert list(iter_added_lines(patch)) == [(11, "added one"), (12, "added two")]


def test_multiple_hunks():
    patch = textwrap.dedent("""\
        @@ -1,2 +1,3 @@
         a
        +b
         c
        @@ -20,2 +21,3 @@
         x
        +y
         z""")
    assert list(iter_added_lines(patch)) == [(2, "b"), (22, "y")]


def test_hunk_without_count_field():
    # GitHub sometimes omits the ",count" — single-line hunks
    patch = "@@ -5 +5 @@\n-old\n+new"
    assert list(iter_added_lines(patch)) == [(5, "new")]


def test_ignores_file_headers_and_no_newline_marker():
    patch = textwrap.dedent("""\
        --- a/file.py
        +++ b/file.py
        @@ -1,2 +1,2 @@
         keep
        -bye
        +hi
        \\ No newline at end of file""")
    assert list(iter_added_lines(patch)) == [(2, "hi")]


def test_empty_patch_yields_nothing():
    assert list(iter_added_lines("")) == []
    assert list(iter_added_lines(None)) == []


def test_addition_line_with_only_plus_sign_yields_empty_content():
    # A blank added line — useful to confirm we don't crash on minimal slices.
    patch = "@@ -1,1 +1,2 @@\n context\n+"
    assert list(iter_added_lines(patch)) == [(2, "")]
```

- [ ] **Step 2: Run tests — verify failure**

Run: `cd /home/action && python -m pytest tests/test_diff_parser.py -v`
Expected: collection error for missing module.

- [ ] **Step 3: Implement `diff_parser.py`**

Write `/home/action/src/diff_parser.py`:

```python
"""Parse unified-diff patches to extract added lines and their new-file line numbers."""
from __future__ import annotations

import re
from typing import Iterable, Iterator

# Matches the new-file portion of a hunk header.
# Examples: "@@ -1,3 +1,4 @@", "@@ -5 +5 @@", "@@ -1,0 +1,3 @@ class Foo:"
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def iter_added_lines(patch: str | None) -> Iterator[tuple[int, str]]:
    """Yield (new_line_number, content) for each added line in `patch`.

    `patch` is a unified-diff string (the value GitHub returns under
    ``files[i].patch``). `content` is the line with its leading ``+`` stripped.
    """
    if not patch:
        return

    new_line = 0
    for raw in patch.splitlines():
        if raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            if not m:
                continue
            # First added line in the hunk gets number int(m.group(1)).
            # We pre-decrement so the first '+' or ' ' line increments to that value.
            new_line = int(m.group(1)) - 1
            continue

        if raw.startswith("+++") or raw.startswith("---"):
            continue  # file headers
        if raw.startswith("\\"):
            continue  # "\ No newline at end of file"

        if raw.startswith("+"):
            new_line += 1
            yield new_line, raw[1:]
        elif raw.startswith("-"):
            # deletion does not advance new-file line counter
            continue
        else:
            # context line (starts with ' ' or is empty)
            new_line += 1
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/action && python -m pytest tests/test_diff_parser.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/action
git add src/diff_parser.py tests/test_diff_parser.py
git commit -m "feat: unified-diff parser yielding added-line numbers"
```

---

## Task 4: Matcher (TDD)

**Files:**
- Create: `/home/action/tests/test_matcher.py`
- Create: `/home/action/src/matcher.py`

`match_line(line, rules)` returns the subset of `rules` triggered by `line` — preserves rule order. String rules trigger when `rule.value in line` (substring); regex rules trigger when `rule.compiled.search(line)` is truthy.

- [ ] **Step 1: Write failing tests**

Write `/home/action/tests/test_matcher.py`:

```python
import re

from src.keywords_loader import Rule
from src.matcher import match_line


def _string(value, message="msg"):
    return Rule(kind="string", value=value, message=message, compiled=None)


def _regex(pattern, message="msg"):
    return Rule(kind="regex", value=pattern, message=message,
                compiled=re.compile(pattern))


def test_string_rule_substring_hit():
    rules = [_string("password")]
    assert match_line("db_password = 'x'", rules) == rules


def test_string_rule_no_hit():
    assert match_line("nothing here", [_string("password")]) == []


def test_regex_rule_search_hit():
    rules = [_regex(r"sk-[a-zA-Z0-9]{4,}")]
    assert match_line("token sk-abcdef", rules) == rules


def test_multiple_rules_all_triggering_preserves_order():
    r1 = _string("TODO", message="todo")
    r2 = _string("password", message="pw")
    r3 = _regex(r"sk-\w+", message="key")
    line = "TODO: password = sk-abcdef"
    assert match_line(line, [r1, r2, r3]) == [r1, r2, r3]


def test_partial_subset_match():
    r1 = _string("password")
    r2 = _string("apikey")
    assert match_line("only password here", [r1, r2]) == [r1]


def test_empty_rule_list():
    assert match_line("anything", []) == []


def test_empty_line():
    assert match_line("", [_string("x"), _regex(r".+")]) == []
```

- [ ] **Step 2: Run tests — verify failure**

Run: `cd /home/action && python -m pytest tests/test_matcher.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `matcher.py`**

Write `/home/action/src/matcher.py`:

```python
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
            if rule.compiled is not None and rule.compiled.search(line):
                hits.append(rule)
    return hits
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/action && python -m pytest tests/test_matcher.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/action
git add src/matcher.py tests/test_matcher.py
git commit -m "feat: per-line rule matcher"
```

---

## Task 5: GitHub Client (TDD)

**Files:**
- Create: `/home/action/tests/test_github_client.py`
- Create: `/home/action/src/github_client.py`

Two functions:
- `get_pr_files(repo, pr_number, token, *, max_files=300)` — paginates `GET /repos/{repo}/pulls/{pr}/files` until either there are no more pages, or `max_files` is reached. Returns `(files, truncated_extra)` where `truncated_extra` is the count of additional files we *know* exist past the cap (0 if we collected them all; positive if a further page existed).
- `post_review(repo, pr_number, token, comments, body, event)` — `POST /repos/{repo}/pulls/{pr}/reviews` with the given comments list, body, and event (`COMMENT`/`APPROVE`/`REQUEST_CHANGES`). Raises `requests.HTTPError` on non-2xx via `response.raise_for_status()`.

Tests mock `requests.get` / `requests.post` via `unittest.mock.patch`.

- [ ] **Step 1: Write failing tests**

Write `/home/action/tests/test_github_client.py`:

```python
from unittest.mock import patch, MagicMock

import pytest
import requests

from src.github_client import get_pr_files, post_review, GITHUB_API


def _resp(json_data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    r.raise_for_status = MagicMock()
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return r


def test_get_pr_files_single_page():
    files = [{"filename": "a.py", "patch": "@@ -1 +1 @@\n+x"}]
    with patch("src.github_client.requests.get", return_value=_resp(files)) as get:
        result, truncated = get_pr_files("octo/hello", 7, "tok")
    assert result == files
    assert truncated == 0
    get.assert_called_once()
    url, = get.call_args.args
    assert url == f"{GITHUB_API}/repos/octo/hello/pulls/7/files"
    assert get.call_args.kwargs["params"] == {"per_page": 100, "page": 1}
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"


def test_get_pr_files_paginates_until_short_page():
    page1 = [{"filename": f"f{i}.py"} for i in range(100)]
    page2 = [{"filename": "f100.py"}]
    with patch("src.github_client.requests.get",
               side_effect=[_resp(page1), _resp(page2)]):
        files, truncated = get_pr_files("o/r", 1, "tok")
    assert len(files) == 101
    assert truncated == 0


def test_get_pr_files_stops_at_max_and_reports_extra():
    full_page = [{"filename": f"f{i}.py"} for i in range(100)]
    extra_page = [{"filename": f"e{i}.py"} for i in range(100)]
    # Pages 1,2,3 (cap) and a 4th page exists with more
    with patch("src.github_client.requests.get",
               side_effect=[_resp(full_page), _resp(full_page),
                            _resp(full_page), _resp(extra_page)]) as get:
        files, truncated = get_pr_files("o/r", 1, "tok", max_files=300)
    assert len(files) == 300
    assert truncated == 100
    # Should call 4 times: 3 to fill the cap + 1 peek to learn the extra count
    assert get.call_count == 4


def test_get_pr_files_raises_on_http_error():
    with patch("src.github_client.requests.get",
               return_value=_resp({"message": "boom"}, status=500)):
        with pytest.raises(requests.HTTPError):
            get_pr_files("o/r", 1, "tok")


def test_post_review_sends_expected_payload():
    comments = [{"path": "a.py", "line": 3, "side": "RIGHT", "body": "msg"}]
    with patch("src.github_client.requests.post",
               return_value=_resp({"id": 42})) as post:
        result = post_review("o/r", 9, "tok", comments=comments,
                             body="summary", event="REQUEST_CHANGES")
    assert result == {"id": 42}
    url, = post.call_args.args
    assert url == f"{GITHUB_API}/repos/o/r/pulls/9/reviews"
    payload = post.call_args.kwargs["json"]
    assert payload == {"body": "summary", "event": "REQUEST_CHANGES",
                       "comments": comments}
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"


def test_post_review_raises_on_http_error():
    with patch("src.github_client.requests.post",
               return_value=_resp({"message": "bad"}, status=422)):
        with pytest.raises(requests.HTTPError):
            post_review("o/r", 1, "tok", comments=[], body="", event="COMMENT")
```

- [ ] **Step 2: Run tests — verify failure**

Run: `cd /home/action && python -m pytest tests/test_github_client.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `github_client.py`**

Write `/home/action/src/github_client.py`:

```python
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
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd /home/action && python -m pytest tests/test_github_client.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/action
git add src/github_client.py tests/test_github_client.py
git commit -m "feat: GitHub REST wrapper with files pagination and review post"
```

---

## Task 6: Orchestrator (TDD)

**Files:**
- Create: `/home/action/tests/conftest.py`
- Create: `/home/action/tests/test_check_keywords.py`
- Create: `/home/action/src/check_keywords.py`

The orchestrator reads env vars, calls each submodule, builds the comment payload, and posts the review. Multiple rules on the same line are merged into a single comment whose body bullets every message (with the rule value shown in backticks). Skipped files (beyond `max_files`) cause a notice appended to the review `body`. Files with no `patch` (binary / too large / deleted) are skipped silently. The `removed` status files are also skipped.

Exit-code conventions:
- `0` — no violations OR violations posted successfully OR keywords.yml missing.
- Non-zero — uncaught exception (HTTP error, malformed env, etc.).

The `--no-violation-action` input is passed through env `NO_VIOLATION_ACTION` and controls the event when there are no hits: `comment` → `COMMENT`, `approve` → `APPROVE`. Anything else falls back to `COMMENT` (with a warning).

- [ ] **Step 1: Write shared fixtures**

Write `/home/action/tests/conftest.py`:

```python
import textwrap
import pytest


@pytest.fixture
def patch_with_password_and_todo():
    """A patch where line 2 (new file) contains 'password' and line 3 contains 'TODO'."""
    return textwrap.dedent("""\
        @@ -1,2 +1,4 @@
         keep me
        +password = "hunter2"
        +# TODO clean up
         tail""")


@pytest.fixture
def sample_keywords_yaml(tmp_path):
    p = tmp_path / "keywords.yml"
    p.write_text(textwrap.dedent("""\
        keywords:
          - type: string
            value: password
            message: hardcoded password
          - type: string
            value: TODO
            message: resolve TODO before merge
    """))
    return str(p)
```

- [ ] **Step 2: Write failing orchestrator tests**

Write `/home/action/tests/test_check_keywords.py`:

```python
from unittest.mock import patch, MagicMock

import pytest

from src import check_keywords as ck


def _env(tmp_path, **overrides):
    base = {
        "GITHUB_TOKEN": "tok",
        "REPO": "octo/hello",
        "PR_NUMBER": "42",
        "KEYWORDS_PATH": str(tmp_path / "missing.yml"),
        "NO_VIOLATION_ACTION": "comment",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return base


def test_no_keywords_file_posts_comment_review(tmp_path):
    files = [{"filename": "a.py", "status": "modified",
              "patch": "@@ -1 +1 @@\n+anything"}]
    with patch.object(ck, "get_pr_files", return_value=(files, 0)) as gpf, \
         patch.object(ck, "post_review", return_value={"id": 1}) as pr:
        rc = ck.main(_env(tmp_path))
    assert rc == 0
    pr.assert_called_once()
    kwargs = pr.call_args.kwargs
    assert kwargs["event"] == "COMMENT"
    assert kwargs["comments"] == []
    gpf.assert_called_once_with("octo/hello", 42, "tok", max_files=300)


def test_violations_produce_request_changes_review(sample_keywords_yaml,
                                                    patch_with_password_and_todo,
                                                    tmp_path):
    files = [{"filename": "app.py", "status": "modified",
              "patch": patch_with_password_and_todo}]
    env = _env(tmp_path, KEYWORDS_PATH=sample_keywords_yaml)
    with patch.object(ck, "get_pr_files", return_value=(files, 0)), \
         patch.object(ck, "post_review", return_value={"id": 9}) as pr:
        rc = ck.main(env)
    assert rc == 0
    kwargs = pr.call_args.kwargs
    assert kwargs["event"] == "REQUEST_CHANGES"
    comments = kwargs["comments"]
    assert len(comments) == 2
    by_line = {c["line"]: c for c in comments}
    assert by_line[2]["path"] == "app.py"
    assert by_line[2]["side"] == "RIGHT"
    assert "hardcoded password" in by_line[2]["body"]
    assert "TODO" in by_line[3]["body"]


def test_multiple_rules_same_line_merged_into_one_comment(tmp_path, sample_keywords_yaml):
    # The single added line contains BOTH "password" and "TODO".
    patch_str = "@@ -1,1 +1,2 @@\n keep\n+password TODO bad"
    files = [{"filename": "x.py", "status": "modified", "patch": patch_str}]
    env = _env(tmp_path, KEYWORDS_PATH=sample_keywords_yaml)
    with patch.object(ck, "get_pr_files", return_value=(files, 0)), \
         patch.object(ck, "post_review", return_value={"id": 1}) as pr:
        ck.main(env)
    comments = pr.call_args.kwargs["comments"]
    assert len(comments) == 1
    body = comments[0]["body"]
    assert "hardcoded password" in body
    assert "resolve TODO before merge" in body


def test_files_without_patch_are_skipped(tmp_path, sample_keywords_yaml):
    files = [
        {"filename": "image.png", "status": "added", "patch": None},
        {"filename": "del.py", "status": "removed", "patch": "@@ -1 +0,0 @@\n-x"},
    ]
    env = _env(tmp_path, KEYWORDS_PATH=sample_keywords_yaml)
    with patch.object(ck, "get_pr_files", return_value=(files, 0)), \
         patch.object(ck, "post_review", return_value={"id": 1}) as pr:
        ck.main(env)
    assert pr.call_args.kwargs["comments"] == []
    assert pr.call_args.kwargs["event"] == "COMMENT"


def test_truncated_files_notice_in_body(tmp_path, sample_keywords_yaml):
    files = [{"filename": "a.py", "status": "modified",
              "patch": "@@ -1 +1,2 @@\n a\n+ok"}]
    env = _env(tmp_path, KEYWORDS_PATH=sample_keywords_yaml)
    with patch.object(ck, "get_pr_files", return_value=(files, 25)), \
         patch.object(ck, "post_review", return_value={"id": 1}) as pr:
        ck.main(env)
    body = pr.call_args.kwargs["body"]
    assert "25" in body
    assert "skipped" in body.lower()


def test_no_violation_action_approve(tmp_path):
    files = [{"filename": "a.py", "status": "modified",
              "patch": "@@ -1 +1,2 @@\n a\n+ok"}]
    env = _env(tmp_path, NO_VIOLATION_ACTION="approve")
    with patch.object(ck, "get_pr_files", return_value=(files, 0)), \
         patch.object(ck, "post_review", return_value={"id": 1}) as pr:
        ck.main(env)
    assert pr.call_args.kwargs["event"] == "APPROVE"


def test_missing_required_env_raises(tmp_path):
    env = _env(tmp_path)
    del env["REPO"]
    with pytest.raises(SystemExit):
        ck.main(env)


def test_pr_number_must_be_integer(tmp_path):
    env = _env(tmp_path, PR_NUMBER="not-a-number")
    with pytest.raises(SystemExit):
        ck.main(env)
```

- [ ] **Step 3: Run tests — verify failure**

Run: `cd /home/action && python -m pytest tests/test_check_keywords.py -v`
Expected: collection error.

- [ ] **Step 4: Implement `check_keywords.py`**

Write `/home/action/src/check_keywords.py`:

```python
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
```

- [ ] **Step 5: Run all tests — verify pass**

Run: `cd /home/action && python -m pytest -v`
Expected: every test PASSES across all five test files (26+ tests total).

- [ ] **Step 6: Commit**

```bash
cd /home/action
git add src/check_keywords.py tests/conftest.py tests/test_check_keywords.py
git commit -m "feat: orchestrator wiring all checker components"
```

---

## Task 7: Composite Action Definition

**Files:**
- Create: `/home/action/action.yml`

We deviate slightly from the spec's `shell: python3 {0}` line — that form treats `run:` as the script body, not a path. The clean idiomatic form is two steps: install dependencies, then invoke the script with `python3`.

- [ ] **Step 1: Write `action.yml`**

Write `/home/action/action.yml`:

```yaml
name: 'Keyword Checker'
description: 'Detect forbidden keywords in PR diffs and post inline review comments.'
author: 'keyword-checker contributors'
branding:
  icon: 'alert-octagon'
  color: 'red'
inputs:
  github-token:
    description: 'GitHub token used to call the API and post reviews.'
    required: true
  keywords-path:
    description: 'Path (in the business repo checkout) to the keywords config file.'
    required: false
    default: '.github/keywords.yml'
  no-violation-action:
    description: 'Review event when no violations are found: "comment" or "approve".'
    required: false
    default: 'comment'
runs:
  using: 'composite'
  steps:
    - name: Install Python dependencies
      shell: bash
      run: |
        python3 -m pip install --quiet --user \
          -r "${{ github.action_path }}/requirements.txt"
    - name: Run keyword check
      shell: bash
      working-directory: ${{ github.action_path }}
      run: python3 -m src.check_keywords
      env:
        GITHUB_TOKEN: ${{ inputs.github-token }}
        KEYWORDS_PATH: ${{ github.workspace }}/${{ inputs.keywords-path }}
        NO_VIOLATION_ACTION: ${{ inputs.no-violation-action }}
        PR_NUMBER: ${{ github.event.pull_request.number }}
        REPO: ${{ github.repository }}
```

Notes for the implementer:
- `working-directory: ${{ github.action_path }}` lets us run `python3 -m src.check_keywords` so relative imports inside the `src/` package work.
- `KEYWORDS_PATH` is resolved against `${{ github.workspace }}` (the business repo checkout), not the action path.
- No need to add `__main__.py`; `python -m src.check_keywords` runs the module's `if __name__ == "__main__"` block.

- [ ] **Step 2: Commit**

```bash
cd /home/action
git add action.yml
git commit -m "feat: composite action.yml with install + run steps"
```

---

## Task 8: CI Test Workflow

**Files:**
- Create: `/home/action/.github/workflows/test.yml`

- [ ] **Step 1: Write workflow**

Write `/home/action/.github/workflows/test.yml`:

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
      - name: Run pytest
        run: python -m pytest -v
```

- [ ] **Step 2: Commit**

```bash
cd /home/action
git add .github/workflows/test.yml
git commit -m "ci: matrix pytest workflow"
```

---

## Task 9: Sample Config + README

**Files:**
- Create: `/home/action/examples/keywords.yml`
- Create: `/home/action/README.md`

- [ ] **Step 1: Write sample config**

Write `/home/action/examples/keywords.yml`:

```yaml
keywords:
  - type: string
    value: "password"
    message: "Hardcoded password detected. Use env vars or a secret manager."
  - type: string
    value: "TODO"
    message: "Please resolve this TODO before merging."
  - type: regex
    value: "sk-[a-zA-Z0-9]{32,}"
    message: "Possible OpenAI API key leak."
  - type: regex
    value: "(?i)secret\\s*=\\s*['\"][^'\"]+['\"]"
    message: "Possible hardcoded secret literal."
```

- [ ] **Step 2: Write README**

Write `/home/action/README.md`:

````markdown
# keyword-checker

A GitHub Actions composite action that scans the **added** lines of a pull
request for forbidden keywords (hard-coded passwords, API keys, lingering
TODOs, …) and posts inline review comments — similar to GitHub Copilot
Code Review.

## Usage

In your business repo, add `.github/workflows/pr-keyword-check.yml`:

```yaml
name: PR Keyword Check
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  check:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/keyword-checker@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

Then add `.github/keywords.yml` (see `examples/keywords.yml`):

```yaml
keywords:
  - type: string
    value: "password"
    message: "Hardcoded password. Use env vars."
  - type: regex
    value: "sk-[a-zA-Z0-9]{32,}"
    message: "Possible OpenAI API key leak."
```

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `github-token` | (required) | Token used for API calls and review submission. |
| `keywords-path` | `.github/keywords.yml` | Path to the keyword config inside the business repo. |
| `no-violation-action` | `comment` | Event when no violations: `comment` or `approve`. |

## Behaviour

- Only **added** lines (`+` in the diff) are scanned.
- Multiple rules triggered on the same line are merged into one comment.
- A missing `keywords.yml` produces a warning but does not fail the check.
- An invalid regex rule is skipped (with a warning); other rules continue.
- PRs with more than 300 changed files have the excess skipped; a notice
  is added to the review body.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```
````

- [ ] **Step 3: Commit**

```bash
cd /home/action
git add README.md examples/keywords.yml
git commit -m "docs: README and sample keywords.yml"
```

---

## Final Verification

- [ ] **Step 1: Run the full test suite one last time**

Run: `cd /home/action && python -m pytest -v`
Expected: every test (loader, parser, matcher, client, orchestrator) PASSES.

- [ ] **Step 2: Lint the action.yml syntax**

Run: `cd /home/action && python3 -c "import yaml; yaml.safe_load(open('action.yml'))" && echo OK`
Expected: prints `OK`.

- [ ] **Step 3: Smoke-check the entrypoint**

Run: `cd /home/action && python3 -c "from src.check_keywords import main; print(main.__doc__ or 'no doc')"`
Expected: prints the module/function help or "no doc" — but no ImportError.

- [ ] **Step 4: Confirm directory tree matches the spec**

Run: `cd /home/action && find . -type f -not -path './.git/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' | sort`
Expected output (order may vary slightly):

```
./.github/workflows/test.yml
./.gitignore
./README.md
./action.yml
./docs/superpowers/plans/2026-06-10-pr-keyword-checker-implementation.md
./docs/superpowers/specs/2026-06-10-pr-keyword-checker-design.md
./examples/keywords.yml
./pytest.ini
./requirements-dev.txt
./requirements.txt
./src/__init__.py
./src/check_keywords.py
./src/diff_parser.py
./src/github_client.py
./src/keywords_loader.py
./src/matcher.py
./tests/__init__.py
./tests/conftest.py
./tests/test_check_keywords.py
./tests/test_diff_parser.py
./tests/test_github_client.py
./tests/test_keywords_loader.py
./tests/test_matcher.py
```

---

## Spec Coverage Self-Check

| Spec requirement | Task |
|------------------|------|
| Composite action runs on self-hosted, Python, no DinD | Task 7 (action.yml — `using: composite`) |
| `pull_request` opened/synchronize trigger | Task 9 README documents the consumer workflow |
| Only scan added lines | Task 3 (`iter_added_lines` yields only `+` lines) |
| Config file format (string/regex/value/message) | Task 2 (loader validates exactly these fields) |
| Read `keywords.yml`, parse rules | Task 2 |
| Fetch PR files via GitHub API | Task 5 (`get_pr_files`) |
| Parse diff, extract added lines + line numbers | Task 3 |
| Match each line against rules | Task 4 |
| Merge multiple-rule hits on one line into one comment | Task 6 (`_format_comment_body`) |
| One review request with all comments | Task 6 + Task 5 (`post_review`) |
| `REQUEST_CHANGES` if any violation, else `COMMENT`/`APPROVE` | Task 6 (`_build_body`) |
| Inputs: github-token, keywords-path, no-violation-action | Task 7 (action.yml) |
| Missing `keywords.yml` → warn + exit 0 | Task 2 + Task 6 (empty rule list ⇒ COMMENT) |
| Invalid regex → skip + warn | Task 2 |
| GitHub API error → fail | Task 5 (`raise_for_status`) |
| Multi-rule same-line merge | Task 6 |
| >300 files → summary comment | Task 5 (peek page) + Task 6 (`_build_body`) |
| Unit-test coverage of all six listed scenarios | Tasks 2, 3, 4, 6 (every scenario has a test) |
