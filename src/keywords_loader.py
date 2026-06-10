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

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError as exc:
        raise ValueError(f"Cannot read keywords config at {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in keywords config at {path}: {exc}") from exc

    raw_rules = data.get("keywords")
    if raw_rules is None:
        raw_rules = []
    if not isinstance(raw_rules, list):
        _warn(f"'keywords' must be a list, got {type(raw_rules).__name__}; "
              f"no rules will be applied")
        return []
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
