"""Tests of tools/check_citations.py on fixtures with good and bad citations.

The fixtures cite pyharp@f34506f9d14ee7b1f2e1222775baa5093ae6967f (chengcli/pyharp main, the base of the tech-report
branch and the report's pin), so they resolve offline in any clone of the branch with its history. Run from the report directory: `python3 -m pytest tools/tests`.
"""

import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(TOOLS))

import check_citations  # noqa: E402

BASE = "f34506f9d14ee7b1f2e1222775baa5093ae6967f"


@pytest.fixture(autouse=True)
def _need_base_commit():
    p = subprocess.run(["git", "-C", str(TOOLS), "cat-file", "-e", f"{BASE}^{{commit}}"], capture_output=True)
    if p.returncode != 0:
        pytest.skip(f"{BASE} is not in this clone (shallow checkout?)")


def run(*names):
    return check_citations.main(["--offline", *(str(FIXTURES / n) for n in names)])


def test_good_citations_pass(capsys):
    assert run("good.qmd", "good.md") == 0
    out, err = capsys.readouterr()
    assert out == ""
    assert "6 citations in 2 files, 0 with problems" in err


@pytest.mark.parametrize("line, message", [
    (1, "line 191 is past the end of src/radiation/bbflux.cpp at f34506f9d14ee7b1f2e1222775baa5093ae6967f (190 lines)"),
    (2, "file src/radiation/nope.cpp does not exist"),
    (3, "URL is not pinned: 'main' is not a sha"),
    (4, "sha f34506f has 7 characters; a URL needs the full 40-character sha"),
    (5, "link text cites lines 2-5 but the URL anchor is #L2-L6"),
    (6, "sha 0000000000000000000000000000000000000000 not found"),
    (7, "STYLE 3.1: path:line@sha never appears in a .qmd file"),
])
def test_bad_qmd_citations_fail(capsys, line, message):
    assert run("bad.qmd") == 1
    out, _ = capsys.readouterr()
    assert any(f"bad.qmd:{line}:" in l and message in l for l in out.splitlines()), out


@pytest.mark.parametrize("line, message", [
    (1, "sha f34506 has 6 characters; use 7 to 40"),
    (2, "give the path from the repository root, not the basename"),
    (3, "line range 9-3 is reversed"),
])
def test_bad_md_citations_fail(capsys, line, message):
    assert run("bad.md") == 1
    out, _ = capsys.readouterr()
    assert any(f"bad.md:{line}:" in l and message in l for l in out.splitlines()), out


def test_every_bad_line_is_reported(capsys):
    assert run("bad.qmd", "bad.md") == 1
    out, err = capsys.readouterr()
    assert "10 citations in 2 files, 10 with problems" in err
