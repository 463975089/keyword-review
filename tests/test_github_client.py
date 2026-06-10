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
