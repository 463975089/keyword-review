import re

import pytest

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


def test_regex_rule_without_compiled_raises():
    """A regex Rule constructed without compiled= must raise, not silently miss."""
    rule = Rule(kind="regex", value=r"sk-\w+", message="key", compiled=None)
    with pytest.raises(ValueError, match="compiled"):
        match_line("token sk-abcdef", [rule])

