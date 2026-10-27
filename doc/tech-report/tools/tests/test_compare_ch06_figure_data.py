"""The ch06 compare checks the figure data too: ch06_run.sh compares mie_accuracy.json and rayleigh_sigma.json with
the committed copies, and in mie_accuracy.json a relative error of Q_ext below 1e-9, the tolerance of check [C1]
(check_ch06_mie.py), equals any other below it; every value at or above it and every other field is compared.

  - the 7 values that differ between the committed file and a rerun on another host (the fresh-clone audit at
    88e75c95, and this test's own rerun) compare equal;
  - a relative error above the floor that changes, or one that crosses it, exits 1;
  - a changed reference value, size parameter or refractive index exits 1.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import copy
import io
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
REPORT = TOOLS.parent
CHECKS = REPORT / "derivation-checks"
sys.path.insert(0, str(TOOLS))

import compare_outputs as co  # noqa: E402

REL = "src/pyharp_report/ch06/data/mie_accuracy.json"
COMMITTED = json.loads((REPORT / REL).read_text())

# (case, index of x): committed value, the value of the rerun. k = 1e-8, 1e-4, 0.1 are cases 0, 1, 2.
RERUN = {(0, 8): (7.351e-09, 2.905e-10), (0, 15): (9.259e-14, 4.33e-14), (0, 22): (1.11e-16, 0.0),
         (1, 15): (3.553e-15, 6.95e-14), (1, 22): (2.665e-15, 2.554e-15),
         (2, 6): (9.226e-13, 1.262e-12), (2, 15): (8.53e-13, 8.585e-13)}


def with_rel_err(changes, doc=COMMITTED):
    d = copy.deepcopy(doc)
    for (c, i), v in changes.items():
        d["cases"][c]["qext_rel_err"][i] = v
    return d


def dumps(doc):
    return json.dumps(doc, indent=1)   # as check_ch06_mie.py writes it


def compare(tmp_path, expected, actual):
    for side, doc in (("e", expected), ("a", actual)):
        (tmp_path / side / REL).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / side / REL).write_text(doc if isinstance(doc, str) else dumps(doc))
    out = io.StringIO()
    bad = co.compare("ch06", tmp_path / "e", tmp_path / "a", [REL], stream=out,
                     host_rules=co.load_host_dependent(CHECKS / "host-dependent.json"))
    return bad, out.getvalue()


def cli(tmp_path, expected, actual):
    compare(tmp_path, expected, actual)
    return co.main(["--host-dependent", str(CHECKS / "host-dependent.json"), "ch06", str(tmp_path / "e"),
                    str(tmp_path / "a"), REL])


def test_the_committed_file_holds_the_values_of_the_rerun_table():
    assert dumps(COMMITTED) == (REPORT / REL).read_text()
    for (c, i), (old, _) in RERUN.items():
        assert COMMITTED["cases"][c]["qext_rel_err"][i] == old, (c, i)


def test_the_rerun_on_another_host_compares_equal(tmp_path):
    rerun = with_rel_err({ci: new for ci, (_, new) in RERUN.items()})
    bad, out = compare(tmp_path, COMMITTED, rerun)
    assert bad == 0, out
    assert "7 line(s) with declared host-dependent values differ" in out
    assert cli(tmp_path, COMMITTED, rerun) == 0


@pytest.mark.parametrize("ci,new", [
    ((2, 0), 2.1e-09),     # k = 0.1, x = 0.01: 1.98e-09 committed, the 2.0e-9 of the Limits
    ((0, 0), 0.0006394),   # k = 1e-8, x = 0.01: the 6.4e-4 of the Limits
    ((0, 9), 1.085e-09),   # just above the floor
    ((2, 15), 1.0e-09),    # below the floor committed (8.53e-13), at the floor regenerated
    ((1, 22), 3.0e-08),    # below the floor committed, far above it regenerated
])
def test_a_relative_error_at_or_above_the_floor_is_compared(tmp_path, ci, new):
    bad, out = compare(tmp_path, COMMITTED, with_rel_err({ci: new}))
    assert bad == 1, out
    assert cli(tmp_path, COMMITTED, with_rel_err({ci: new})) == 1


def test_a_value_above_the_floor_fails_next_to_the_rerun_values(tmp_path):
    rerun = with_rel_err({ci: new for ci, (_, new) in RERUN.items()})
    assert cli(tmp_path, COMMITTED, with_rel_err({(2, 0): 2.1e-09}, rerun)) == 1


@pytest.mark.parametrize("field,c,i,new", [
    ("qext_ref", 0, 0, 1.3346042942e-09),
    ("g_ref", 2, 32, 0.5),
    ("x", None, 4, 0.0316),
    ("k", 1, None, 0.001),
    ("n", 0, None, 1.34),
])
def test_a_change_outside_the_relative_errors_fails(tmp_path, field, c, i, new):
    d = copy.deepcopy(COMMITTED)
    if c is None:
        d[field][i] = new
    elif i is None:
        d["cases"][c][field] = new
    else:
        d["cases"][c][field][i] = new
    bad, out = compare(tmp_path, COMMITTED, d)
    assert bad == 1, out
    assert cli(tmp_path, COMMITTED, d) == 1


def test_a_missing_value_or_a_broken_file_fails(tmp_path):
    d = copy.deepcopy(COMMITTED)
    d["cases"][0]["qext_rel_err"].pop()
    assert compare(tmp_path, COMMITTED, d)[0] == 1
    assert compare(tmp_path, COMMITTED, dumps(COMMITTED)[:-40])[0] == 1


def test_the_floor_needs_a_value_and_applies_only_to_its_lines():
    rules = co.rules_for(co.load_host_dependent(CHECKS / "host-dependent.json"), REL)
    assert [m for _, m, _ in rules] == [["values"], ["floor"]]
    line, n = co.mask_host("cases[1].qext_rel_err[22]: 2.665e-15", rules)
    assert (line, n) == ("cases[1].qext_rel_err[22]: <below 1e-09>", 1)
    assert co.mask_host("cases[0].qext_ref[0]: 1.3346042941e-09", rules) == ("cases[0].qext_ref[0]: 1.3346042941e-09", 0)
    assert co.mask_host("cases[0].g_ref[3]: 1e-10", rules)[1] == 0


def test_a_floor_entry_is_refused_without_a_floor(tmp_path):
    bad = {"files": {"x.json": [{"lines": "a", "mask": ["floor"], "why": "w", "evidence": "e"}]}}
    (tmp_path / "hd.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        co.load_host_dependent(tmp_path / "hd.json")


def test_ch06_run_compares_the_figure_data():
    text = (CHECKS / "ch06_run.sh").read_text()
    assert "compare.sh" in text and "\ncompare_outputs ch06" in text
    assert "src/pyharp_report/ch06/data/{rayleigh_sigma,mie_accuracy}.json" in text
