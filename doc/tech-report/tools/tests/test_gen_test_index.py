"""Tests of tools/gen_test_index.py, the Appendix C generator, on a small `ctest --show-only=json-v1` fixture.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import json
import random
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(TOOLS))

import gen_test_index as g  # noqa: E402

PIN = "e894700ff7aee30b52882e5202b16461413780b0"


def fixture_of(info):
    tests, external = g.reduce_ctest_json(info, "/src", "/src/build")
    return {"format": g.FORMAT, "repository": g.REPOSITORY, "pin": PIN, "ctest_version": "3.30.0",
            "configure": "-DCMAKE_BUILD_TYPE=Release", "registered": len(tests) + sum(external.values()),
            "external": external, "tests": sorted(tests, key=lambda t: t["name"])}


@pytest.fixture
def info():
    return json.loads((FIXTURES / "ctest-json-v1.json").read_text())


def test_reduce_keeps_the_package_tests_and_their_call_sites(info):
    tests, external = g.reduce_ctest_json(info, "/src", "/src/build")
    assert external == {"eigen": 1}
    by_name = {t["name"]: t for t in tests}
    assert sorted(by_name) == ["test_eos.release", "test_seam_gloo"]
    # through setup_test: the call in tests/CMakeLists.txt, not the add_test inside the macro
    assert by_name["test_eos.release"]["defined_at"] == "tests/CMakeLists.txt:7"
    assert by_name["test_eos.release"]["via"] == "setup_test"
    assert by_name["test_seam_gloo"]["defined_at"] == "tests/CMakeLists.txt:133"
    # machine-specific properties (paths, environment) are dropped
    assert by_name["test_seam_gloo"]["properties"] == {"LABELS": ["exchange", "decomp"], "SKIP_RETURN_CODE": 125}


def test_fragment_rows_links_and_header(info):
    text = g.fragment(fixture_of(info))
    assert f"pin: {g.REPOSITORY} {PIN}" in text
    assert "`ctest -N` lists 3; the other 1 are the test suites of dependencies the build fetches (eigen: 1)" in text
    rows = [l for l in text.splitlines() if l.startswith("| `")]
    assert rows == [
        f"| `test_eos.release` | — | `setup_test` ([`tests/CMakeLists.txt:7`](https://github.com/{g.REPOSITORY}/blob/{PIN}"
        "/tests/CMakeLists.txt#L7)) | expected to fail |",
        f"| `test_seam_gloo` | exchange, decomp | `add_test` ([`tests/CMakeLists.txt:133`](https://github.com/"
        f"{g.REPOSITORY}/blob/{PIN}/tests/CMakeLists.txt#L133)) | skips on exit 125 |",
    ]
    assert text.rstrip().endswith("{#tbl-appc-tests}")


def test_fragment_does_not_depend_on_ctest_order(info):
    first = g.fragment(fixture_of(info))
    random.Random(1).shuffle(info["tests"])
    assert g.fragment(fixture_of(info)) == first


def test_check_passes_on_a_clean_fixture_and_fails_on_a_tampered_one(info, tmp_path, capsys):
    fx, fr = tmp_path / "ctest-index.json", tmp_path / "_appc-test-index.qmd"
    fx.write_text(g._dump(fixture_of(info)))
    assert g.main(["--fixture", str(fx), "--fragment", str(fr)]) == 0
    assert g.main(["--check", "--fixture", str(fx), "--fragment", str(fr)]) == 0
    tampered = json.loads(fx.read_text())
    tampered["tests"][0]["properties"]["LABELS"] = ["eos"]                 # the fixture changes ...
    fx.write_text(g._dump(tampered))
    capsys.readouterr()
    assert g.main(["--check", "--fixture", str(fx), "--fragment", str(fr)]) == 1   # ... the fragment did not
    out = capsys.readouterr().out
    assert "+| `test_eos.release` | eos |" in out and "-| `test_eos.release` | — |" in out


def test_check_fails_on_a_hand_edited_fragment(info, tmp_path):
    fx, fr = tmp_path / "ctest-index.json", tmp_path / "_appc-test-index.qmd"
    fx.write_text(g._dump(fixture_of(info)))
    g.main(["--fixture", str(fx), "--fragment", str(fr)])
    fr.write_text(fr.read_text().replace("expected to fail", "flaky"))
    assert g.main(["--check", "--fixture", str(fx), "--fragment", str(fr)]) == 1


def test_plain_ctest_n_output():
    assert g.parse_ctest_n((FIXTURES / "ctest-N.txt").read_text()) == ["rand", "test_eos.release", "test_seam_gloo"]


def test_the_committed_index_is_current():
    assert g.main(["--check"]) == 0
