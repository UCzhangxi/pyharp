"""ch09 D1: the intermittent abort of the whole suite in a drifted build is one verdict, "ended abnormally in k of N".

check_ch09_d1.sh runs the whole suite of a "-drift" environment N times (D1_FULL_RUNS) and prints one line; the
comparison (host-dependent.json, mask `abnormal_runs`) keeps N and the verdict, EXPECTED-FAIL for k >= 1 and PASS
for k = 0, and masks k and the per-run record. These tests run the real check script against a stub `python` that
plays pytest with a chosen sequence of aborting and clean runs, then compare two such outputs.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
CHECKS = TOOLS.parent / "derivation-checks"
sys.path.insert(0, str(TOOLS))

import compare_outputs as co  # noqa: E402

pytestmark = pytest.mark.skipif(not (shutil.which("bash") and shutil.which("timeout")), reason="needs bash, timeout")

STUB = r'''#!/bin/bash
# plays `python` for check_ch09_d1.sh: pydisort version, env line, and pytest with aborts taken from $STUB_PATTERN
case "$*" in
  *"pytest --version"*) echo "pytest 9.1.1"; exit 0 ;;
  *"import pydisort"*) case "$STUB_ENV" in 171|1813b-171-drift) echo 1.7.1 ;; *) echo 1.8.13 ;; esac; exit 0 ;;
  *env_line*) echo "environment: stub $STUB_ENV"; exit 0 ;;
esac
defect=0; [ "$STUB_ENV" = 171b-1813-drift ] && [ "${STUB_DEFECT:-1}" = 1 ] && defect=1
abort() { echo "$1" >&2; exit 134; }
case "$*" in
  *"test_rayleigh.py::test_radiation_band"*) echo "1 passed in 0.10s"; [ $defect = 1 ] && abort "double free or corruption (!prev)"; exit 0 ;;
  *"test_rayleigh.py::"*) echo "1 passed in 0.10s"; exit 0 ;;
  *test_rayleigh.py*) echo "2 passed in 0.20s"; [ $defect = 1 ] && abort "double free or corruption (!prev)"; exit 0 ;;
esac
# the whole suite: in the defective environment, abort or not by the next character of the pattern (1 = abort,
# h = hang until killed); elsewhere never
echo "9 failed, 188 passed in 1.00s"
if [ $defect = 1 ]; then
  i=$(cat "$STUB_COUNTER" 2>/dev/null || echo 0); echo $((i + 1)) > "$STUB_COUNTER"
  c=${STUB_PATTERN:$((i % ${#STUB_PATTERN})):1}
  [ "$c" = 1 ] && abort "corrupted size vs. prev_size"
  [ "$c" = h ] && exec sleep 30
fi
exit 1
'''


def run_check(tmp_path, pattern, defect=True, full_runs=10, timeout=600):
    """Run check_ch09_d1.sh with the stub; return its stdout."""
    d = tmp_path / f"run-{pattern}-{int(defect)}-{full_runs}-{timeout}"
    (d / "bin").mkdir(parents=True)
    (d / "bin" / "python").write_text(STUB)
    (d / "bin" / "python").chmod(0o755)
    (d / "setup.sh").write_text(f'export STUB_ENV="$1"; export PATH="{d / "bin"}:$PATH"\n')
    envs = []
    for name in ["171", "1813", "171b-1813-drift", "1813b-171-drift"]:
        (d / name).mkdir()
        envs.append(f"{name}={d / name}")
    env = dict(os.environ, PATH=f"{d / 'bin'}:/usr/bin:/bin", D1_SETUP=str(d / "setup.sh"), N="3",
               D1_FULL_RUNS=str(full_runs), D1_TIMEOUT=str(timeout), STUB_PATTERN=pattern,
               STUB_DEFECT="1" if defect else "0", STUB_COUNTER=str(d / "counter"))
    r = subprocess.run(["bash", str(CHECKS / "check_ch09_d1.sh"), *envs], env=env, capture_output=True, text=True,
                       timeout=300)
    return r.stdout


def compare(tmp_path, expected, actual):
    for side, text in (("e", expected), ("a", actual)):
        (tmp_path / side).mkdir(exist_ok=True)
        (tmp_path / side / "check_ch09_d1.out").write_text(text)
    out = io.StringIO()
    rules = co.load_host_dependent(CHECKS / "host-dependent.json")
    bad = co.compare("ch09", tmp_path / "e", tmp_path / "a", ["check_ch09_d1.out"], stream=out, host_rules=rules)
    return bad, out.getvalue()


def full_line(text, env="171b-1813-drift"):
    return [l for l in text.splitlines() if f"env {env} " in l and "full" in l]


# (a) a host where some runs are clean still reproduces
def test_some_clean_runs_still_reproduce(tmp_path):
    committed = run_check(tmp_path, "1111111111")
    host = run_check(tmp_path, "1011010001")
    bad, out = compare(tmp_path, committed, host)
    assert bad == 0, out


def test_one_abort_in_n_is_enough(tmp_path):
    bad, out = compare(tmp_path, run_check(tmp_path, "1111111111"), run_check(tmp_path, "0000000001"))
    assert bad == 0, out


# (b) the defect removed: all N runs clean fails
def test_all_runs_clean_fails(tmp_path):
    committed = run_check(tmp_path, "1101101111")
    clean = run_check(tmp_path, "0000000000")
    bad, out = compare(tmp_path, committed, clean)
    assert bad == 1 and "NOT REPRODUCED" in out
    assert "PASS env 171b-1813-drift (pydisort 1.8.13) full suite, 10 runs: ended abnormally" in out


def test_all_runs_clean_line_and_verdict(tmp_path):
    [line] = full_line(run_check(tmp_path, "0000000000"))
    assert re.search(r"\] PASS .* full suite, 10 runs: ended abnormally \(abort, crash or hung\) in 0 of 10; "
                     r"exit codes \[1(, 1){9}\]; aborts: none$", line), line


# (c) the old single-run form and the new form
def test_the_drift_full_suite_is_one_line_with_k_of_n(tmp_path):
    out = run_check(tmp_path, "1101101111")
    lines = full_line(out)
    assert len(lines) == 1, lines
    assert re.search(r"^\[C16\] EXPECTED-FAIL env 171b-1813-drift \(pydisort 1\.8\.13\) full suite, 10 runs: "
                     r"ended abnormally \(abort, crash or hung\) in 8 of 10; exit codes \[134, 134, 1, 134, 134, 1, "
                     r"134, 134, 134, 134\]; aborts: corrupted size vs\. prev_size x8$", lines[0]), lines[0]


def test_the_committed_output_has_the_new_form():
    committed = (CHECKS / "check_ch09_d1.out").read_text()
    [line] = full_line(committed)
    assert line.startswith("[C16] EXPECTED-FAIL env 171b-1813-drift (pydisort 1.8.13) full suite, 10 runs: ")
    assert not any(re.search(r"171b-1813-drift .*full run \d+:", l) for l in committed.splitlines())


def test_the_old_single_run_form_against_the_new_form_differs(tmp_path):
    old = ("[C16] EXPECTED-FAIL env 171b-1813-drift (pydisort 1.8.13) full run 2: exit 134; no summary; "
           "abort: corrupted size vs. prev_size\n")
    new = ("[C16] EXPECTED-FAIL env 171b-1813-drift (pydisort 1.8.13) full suite, 10 runs: ended abnormally "
           "(abort, crash or hung) in 7 of 10; exit codes [134, 1, 134, 134, 1, 134, 134, 1, 134, 134]; "
           "aborts: corrupted size vs. prev_size x7\n")
    assert compare(tmp_path, old, new)[0] == 1


# guards
def test_n_is_compared(tmp_path):
    assert compare(tmp_path, run_check(tmp_path, "1111111111"), run_check(tmp_path, "11111", full_runs=5))[0] == 1


def test_a_hung_run_counts_as_abnormal(tmp_path):
    [line] = full_line(run_check(tmp_path, "h00", full_runs=3, timeout=2))
    assert "] EXPECTED-FAIL " in line and "in 1 of 3" in line and "hung (killed after 2 s)" in line, line


def test_the_matched_and_reverse_environments_are_still_compared_run_by_run(tmp_path):
    out = run_check(tmp_path, "1111111111")
    assert len([l for l in out.splitlines() if re.search(r"env (171|1813) .* full run \d+:", l)]) == 6
    [rev] = full_line(out, "1813b-171-drift")
    assert "] PASS " in rev and "in 0 of 10" in rev
    changed = out.replace("[C20] PASS env 1813b-171-drift", "[C20] EXPECTED-FAIL env 1813b-171-drift")
    assert changed != out and compare(tmp_path, out, changed)[0] == 1


def test_the_drift_rayleigh_and_isolation_runs_keep_their_verdicts(tmp_path):
    out = run_check(tmp_path, "1111111111")
    clean = run_check(tmp_path, "1111111111", defect=False)
    assert compare(tmp_path, out, clean)[0] == 1
    assert len([l for l in out.splitlines() if "171b-1813-drift (pydisort 1.8.13) rayleigh run" in l
                and "EXPECTED-FAIL" in l]) == 3


def test_the_declaration_matches_the_committed_line_and_carries_evidence():
    spec = json.loads((CHECKS / "host-dependent.json").read_text())["files"]["check_ch09_d1.out"]
    entry = next(e for e in spec if "abnormal_runs" in e["mask"])
    assert "of" in entry["evidence"] and entry["why"]
    committed = (CHECKS / "check_ch09_d1.out").read_text().splitlines()
    assert sum(bool(re.search(entry["lines"], l)) for l in committed) == 2
