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
