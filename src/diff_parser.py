"""Parse unified-diff patches to extract added lines and their new-file line numbers."""
from __future__ import annotations

import re
from typing import Iterator

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
