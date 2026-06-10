from unittest.mock import patch

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
