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
