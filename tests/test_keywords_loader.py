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


def test_keywords_must_be_list_or_returns_empty(tmp_path, capsys):
    # YAML allows `keywords: "password"` (string) or `keywords: 42` (int) by accident.
    # The loader should reject these with a single clear warning, not iterate
    # character-by-character and spam warnings.
    path_str = write_yaml(tmp_path, "keywords: password\n")
    rules = load_rules(str(path_str))
    assert rules == []
    err = capsys.readouterr().err
    assert "list" in err.lower()
    # Make sure we did NOT spam per-character warnings.
    assert err.lower().count("skipping") <= 1

    path_int = write_yaml(tmp_path, "keywords: 42\n")
    rules = load_rules(str(path_int))
    assert rules == []
    err = capsys.readouterr().err
    assert "list" in err.lower()
    assert err.lower().count("skipping") <= 1


def test_malformed_yaml_raises_value_error(tmp_path):
    """A syntactically invalid YAML file should raise ValueError, not a raw YAMLError."""
    path = tmp_path / "keywords.yml"
    path.write_text("keywords:\n  - type: string\n    value: [unclosed\n")
    with pytest.raises(ValueError, match="[Ii]nvalid YAML"):
        load_rules(str(path))


def test_unreadable_file_raises_value_error(tmp_path):
    """An OSError opening the config file should raise ValueError."""
    from unittest.mock import patch, mock_open
    path = tmp_path / "keywords.yml"
    path.write_text("keywords: []\n")
    with patch("builtins.open", side_effect=PermissionError("Permission denied")):
        with pytest.raises(ValueError, match="[Cc]annot read"):
            load_rules(str(path))


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

