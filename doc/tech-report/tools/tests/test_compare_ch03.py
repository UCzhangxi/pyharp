"""Tests of the ch03 comparison (ch03_run.sh -> compare.sh -> tools/compare_outputs.py): what host-dependent.json
declares for ch03, and that a changed ch03 result still fails.

The differences a fresh-clone audit on another host reported against the committed ch03 outputs (tech-report
88e75c95, both pydisort pins) were: round-off values in ch03_beam_closure [C1]/[C2] (0.0e+00 committed, 2.2e-16)
and ch03_ordinates_algebra [C2]/[C6] (2.7e-15 committed, 2.1e-15), and the crash record of the overflow probes in
ch03_candidates ([-11, -6] with one hang at exit against [-6]). Those must compare equal; a changed verdict, a
changed abnormal-exit count or a value beyond the round-off band must not.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import io
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
CHECKS = TOOLS.parent / "derivation-checks"
sys.path.insert(0, str(TOOLS))

import compare_outputs as co  # noqa: E402

HOST_DEPENDENT = CHECKS / "host-dependent.json"
CH03 = sorted(CHECKS.glob("ch03_*.out"))
BEAM = "ch03_beam_closure.pydisort-1.7.1.out"
ALGEBRA = "ch03_ordinates_algebra.out"
CAND = "ch03_candidates.pydisort-1.7.1.out"


def compare(tmp_path, files):
    """files: {name: (committed text, regenerated text)} -> (number differing, printed report)"""
    for side, i in (("e", 0), ("a", 1)):
        (tmp_path / side).mkdir(exist_ok=True)
        for name, texts in files.items():
            (tmp_path / side / name).write_text(texts[i])
    out = io.StringIO()
    bad = co.compare("ch03", tmp_path / "e", tmp_path / "a", list(files), stream=out,
                     host_rules=co.load_host_dependent(HOST_DEPENDENT))
    return bad, out.getvalue()


def committed(name):
    return (CHECKS / name).read_text()


def edit(text, old, new):
    assert old in text, old
    return text.replace(old, new, 1)


def audit_host(name):
    """the committed output as the audit host regenerated it (the reported differences only)"""
    t = committed(name)
    if name.startswith("ch03_beam_closure"):
        for c in ("[C1] PASS Beer-Lambert via pyharp: max rel dev F_dn 0.0e+00",
                  "[C2] PASS Beer-Lambert via pydisort: max rel dev F_dn 0.0e+00"):
            t = edit(t, c, c.replace("0.0e+00", "2.2e-16"))
    elif name == ALGEBRA:
        t = edit(t, "max rel dev 2.7e-15 (tol 1e-10)", "max rel dev 2.1e-15 (tol 1e-10)")
        t = edit(t, "homogeneous solutions residual 2.4e-15", "homogeneous solutions residual 2.1e-15")
    elif name.startswith("ch03_candidates"):
        line = next(l for l in t.splitlines() if l.startswith("[P2]"))
        codes = line.split("return codes ")[1].split("]")[0] + "]"
        t = edit(t, line, line.replace(f"return codes {codes}",
                                       "return codes [-11, -6], 1 hung at exit (killed after 120 s)"))
    return t


def test_the_ch03_outputs_are_found():
    assert len(CH03) == 13


@pytest.mark.parametrize("path", CH03, ids=lambda p: p.name)
def test_every_committed_ch03_output_reproduces_itself(tmp_path, path):
    text = path.read_text()
    assert compare(tmp_path, {path.name: (text, text)})[0] == 0


# --- RED on the old code: the audit host's differences are declared, so they compare equal --------------------
@pytest.mark.parametrize("name", [BEAM, "ch03_beam_closure.pydisort-1.8.13.out", ALGEBRA, CAND,
                                  "ch03_candidates.pydisort-1.8.13.out"])
def test_the_audit_host_differences_reproduce(tmp_path, name):
    bad, out = compare(tmp_path, {name: (committed(name), audit_host(name))})
    assert bad == 0, out
    assert "differ only in declared host-dependent values" in out


def test_the_whole_chapter_as_the_audit_host_ran_it_reproduces(tmp_path):
    names = [p.name for p in CH03 if "1.8.13" not in p.name]
    bad, out = compare(tmp_path, {n: (committed(n), audit_host(n)) for n in names})
    assert bad == 0, out
    assert out.rstrip().endswith("every label, verdict and tolerance matches)")


@pytest.mark.parametrize("record", [
    "return codes [-11]",                                                  # every run a segmentation fault
    "return codes [-11, -6, 1]",                                           # cdisort's exit(1) also ends it abnormally
    "return codes [], 10 hung at exit (killed after 120 s)",               # every run hung at exit
    "return codes [-6], 3 hung at exit (killed after 60 s)",
])
def test_crashed_and_hung_are_the_same_verdict(tmp_path, record):
    t = committed(CAND)
    assert compare(tmp_path, {CAND: (t, t.replace("return codes [-6]", record))})[0] == 0


# --- GREEN guards: these exit 1 on the old code and must still exit 1 -------------------------------------------
@pytest.mark.parametrize("old,new", [
    ("abnormal exit in 10 of 10 runs, return codes [-6]",                  # one run clean: crashed -> clean
     "abnormal exit in 9 of 10 runs, return codes [-6, 0]"),
    ("abnormal exit in 10 of 10 runs, return codes [-6]",                  # every run clean
     "abnormal exit in 0 of 10 runs, return codes [0]"),
    ("[P2] CANDIDATE reproduced", "[P2] CANDIDATE not reproduced"),
    ("max |dF| against nmom 4 when the fluxes came back: 2.2e-09",         # a value on the probe line
     "max |dF| against nmom 4 when the fluxes came back: 2.3e-09"),
    ("top F_up 0.5606 -> 0.6416", "top F_up 0.5606 -> 0.5606"),
])
def test_a_changed_probe_verdict_or_value_fails(tmp_path, old, new):
    t = committed(CAND)
    assert compare(tmp_path, {CAND: (t, edit(t, old, new))})[0] == 1


@pytest.mark.parametrize("name,old,new", [
    (BEAM, "F_dn 0.0e+00, max F_up/(mu0 F0) 0.0e+00 (tol 1e-12; 24 cases)",      # 2e-14 > 64 eps: still PASS for
     "F_dn 2.0e-14, max F_up/(mu0 F0) 0.0e+00 (tol 1e-12; 24 cases)"),           # the check, not round-off
    (BEAM, "[C1] PASS Beer-Lambert via pyharp: max rel dev F_dn 0.0e+00",
     "[C1] FAIL Beer-Lambert via pyharp: max rel dev F_dn 3.0e-12"),
    (ALGEBRA, "max rel dev 2.7e-15 (tol 1e-10)", "max rel dev 1.5e-14 (tol 1e-10)"),
    (ALGEBRA, "homogeneous solutions residual 2.4e-15 (tol 1e-13)", "homogeneous solutions residual 5.0e-14 (tol 1e-13)"),
    (ALGEBRA, "[C6] PASS homogeneous", "[C6] FAIL homogeneous"),
    (ALGEBRA, "(tol 1e-13)", "(tol 1e-12)"),                                      # the tolerance is compared
])
def test_a_value_beyond_the_roundoff_band_or_a_changed_verdict_fails(tmp_path, name, old, new):
    t = committed(name)
    assert compare(tmp_path, {name: (t, edit(t, old, new))})[0] == 1


def test_the_roundoff_band_is_64_eps_and_below_every_declared_threshold():
    assert co.ROUNDOFF_64EPS == 64 * 2.0 ** -52
    # the strictest threshold among the declared ch03 lines is [C6]'s 1e-13: a value between 64 eps and it is
    # still compared digit for digit, and one above it flips the check's verdict
    assert co.ROUNDOFF_64EPS < 1e-13 / 7


def test_the_ch03_masks_apply_only_to_their_lines(tmp_path):
    # delta_m [C3] is round-off too, but undeclared, and its own tolerance (1e-14) is below the 64 eps band
    other = "ch03_delta_m.pydisort-1.7.1.out"
    t = committed(other)
    assert compare(tmp_path, {other: (t, edit(t, "on and off: max rel dev 0.0e+00", "on and off: max rel dev 2.2e-16"))})[0] == 1


def test_ch03_run_compares_every_committed_output():
    run = (CHECKS / "ch03_run.sh").read_text()
    assert 'source "$D/compare.sh"' in run and 'snapshot_outputs "${OUTS[@]}"' in run
    assert 'compare_outputs "ch03 (pydisort $V)"' in run
    outs = next(l for l in run.splitlines() if l.startswith("OUTS="))
    for v in ("1.7.1", "1.8.13"):
        listed = subprocess.run(["bash", "-c", f'V={v}; {outs}; printf "%s\\n" "${{OUTS[@]}}"'], capture_output=True,
                                text=True, check=True).stdout.split()
        assert sorted(listed) == sorted(p.name for p in CH03 if v in p.name or "pydisort" not in p.name)


def test_cli_exit_status_for_the_audit_host_and_a_perturbed_verdict(tmp_path):
    for side in ("e", "a", "p"):
        (tmp_path / side).mkdir()
    (tmp_path / "e" / CAND).write_text(committed(CAND))
    (tmp_path / "a" / CAND).write_text(audit_host(CAND))
    (tmp_path / "p" / CAND).write_text(edit(committed(CAND), "[P1] CANDIDATE reproduced", "[P1] CANDIDATE not reproduced"))
    tool = [sys.executable, str(TOOLS / "compare_outputs.py"), "--host-dependent", str(HOST_DEPENDENT), "ch03"]
    assert subprocess.run(tool + [str(tmp_path / "e"), str(tmp_path / "a"), CAND], capture_output=True).returncode == 0
    assert subprocess.run(tool + [str(tmp_path / "e"), str(tmp_path / "p"), CAND], capture_output=True).returncode == 1
