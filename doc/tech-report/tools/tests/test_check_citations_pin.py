"""tools/check_citations.py on links at the report's pin, chengcli/pyharp f34506f9d14ee7b1f2e1222775baa5093ae6967f (code_pin.yml).

fixtures/pin.qmd holds one good link (`bbflux_wavelength`, lines 164-166 of src/radiation/bbflux.cpp), one
with a sha that does not exist and one whose lines run past the end of the file (190 lines at the pin). The pin is
in the clone holding this report; the bad sha sends the checker to its cache clone of chengcli/pyharp, so this
test needs the network unless that cache (CHECK_CITATIONS_CACHE) already holds it. Run from the report directory:
`python3 -m pytest tools/tests`.
"""

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pin.qmd"
sys.path.insert(0, str(TOOLS))

import check_citations  # noqa: E402

PIN = "f34506f9d14ee7b1f2e1222775baa5093ae6967f"


@pytest.fixture(scope="module")
def problems():
    """{fixture line: [messages]} from one run of the checker over pin.qmd."""
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        status = check_citations.main([str(FIXTURE)])
    found = {}
    for line in out.getvalue().splitlines():
        n = int(line.split(":", 2)[1])
        found.setdefault(n, []).append(line)
    if any("could not clone" in m or "not found in chengcli/pyharp" in m for m in found.get(1, [])):
        pytest.skip(f"the pin {PIN} cannot be reached (no network and no cache clone)")
    return status, found


def test_the_good_link_passes(problems):
    _, found = problems
    assert 1 not in found, found[1]


def test_a_sha_that_does_not_exist_fails(problems):
    status, found = problems
    assert status == 1
    assert any("sha f34506f9d14ee7b1f2e1222775baa5093ae69670 not found in chengcli/pyharp" in m
               for m in found.get(2, [])), found


def test_lines_past_the_end_fail(problems):
    status, found = problems
    assert status == 1
    assert any(f"line 200 is past the end of src/radiation/bbflux.cpp at {PIN} (190 lines)" in m
               for m in found.get(3, [])), found
