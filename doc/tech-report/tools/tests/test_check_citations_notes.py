"""Note references of STYLE 3.2 in a .qmd (editor's ruling 1791657615): `docs/<file>@<full sha>` (pyharp's docs/) is exempt
from the code-citation form of STYLE 3.1, and only that form. The sha must be the full 40 characters and the file
must exist at it; a short sha, a file outside docs/, or a line range is not a note reference.

fixtures/notes.qmd, by line: 1 note at the pin (passes); 2 the same with a short sha; 3 a script with an output
label (passes); 4 a note that does not exist at the sha; 5 a code file in the note form; 6 a note with lines.
Needs the network unless CHECK_CITATIONS_CACHE holds the pin. Run from the report directory:
`python3 -m pytest tools/tests`.
"""

import contextlib
import io
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "notes.qmd"
sys.path.insert(0, str(TOOLS))

import check_citations  # noqa: E402


@pytest.fixture(scope="module")
def found():
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        status = check_citations.main([str(FIXTURE)])
    lines = {}
    for line in out.getvalue().splitlines():
        lines.setdefault(int(line.split(":", 2)[1]), []).append(line)
    if any("could not clone" in m or "not found in" in m for ms in lines.values() for m in ms):
        pytest.skip("the pin cannot be reached (no network and no cache clone)")
    return status, lines


def test_note_references_at_a_full_sha_pass(found):
    _, lines = found
    assert 1 not in lines, lines[1]
    assert 3 not in lines, lines[3]


def test_a_note_reference_with_a_short_sha_fails(found):
    status, lines = found
    assert status == 1
    assert any("note reference needs the full 40-character sha" in m for m in lines.get(2, [])), lines


def test_a_note_reference_must_exist_at_its_sha(found):
    assert any("file docs/no-such-note.md does not exist" in m for m in found[1].get(4, [])), found[1]


def test_only_docs_files_without_lines_are_notes(found):
    for line in (5, 6):
        assert any("path:line@sha never appears in a .qmd file" in m for m in found[1].get(line, [])), found[1]
