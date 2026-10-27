"""Tests of tools/compare_outputs.py: what the chapter comparison normalises, and that a changed check result fails.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import io
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
CHECKS = TOOLS.parent / "derivation-checks"
sys.path.insert(0, str(TOOLS))

import compare_outputs as co  # noqa: E402

HOST_DEPENDENT = CHECKS / "host-dependent.json"
COMMITTED = sorted(p for p in CHECKS.rglob("*.out") if p.name.startswith(("check_ch05", "check_ch09", "ch08_"))
                   or p.parent.name == "ch10")


def run(tmp_path, expected, actual, **kw):
    (tmp_path / "e").mkdir(exist_ok=True)
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "e" / "x.out").write_text(expected)
    (tmp_path / "a" / "x.out").write_text(actual)
    out = io.StringIO()
    bad = co.compare("chXX", tmp_path / "e", tmp_path / "a", ["x.out"], stream=out, **kw)
    return bad, out.getvalue()


def test_the_committed_outputs_are_found():
    assert len(COMMITTED) >= 30


@pytest.mark.parametrize("path", COMMITTED, ids=lambda p: p.name)
def test_every_committed_output_reproduces_itself(tmp_path, path):
    text = path.read_text()
    assert run(tmp_path, text, text)[0] == 0


# --- what is normalised: the lines a fresh clone on another host changes --------------------------------------
HOST_A = """versions: python 3.11.13, torch 2.10.0+cu126, numpy 2.4.6, pyharp 2.7.9.dev0+gf34506f9d.d20261022, pydisort 1.7.1; CUDA 12.6, NVIDIA GeForce GTX 1080 Ti
environment: pyharp source f34506f9d14ee7b1f2e1222775baa5093ae6967f; CPU AMD Ryzen 9 7950X 16-Core Processor, 32 logical; gcc 11.5.0
host: x86_64, 32 logical CPUs, torch default threads 16
[C1] INFO 1 thread(s), 50 layers, 256 columns: Toon SW: 4.0 us/column (1.0 x Toon SW)
[C13] INFO 16 thread(s), 50 layers, 256 columns: Toon SW: 1.2 us/column (1.0 x Toon SW)
[C14] INFO 16 thread(s), 50 layers, 256 columns: DISORT SW nstr=64: 1467.2 us/column (1260.0 x Toon SW)
env 171: environment: pyharp source f34506f9d14ee7b1f2e1222775baa5093ae6967f; GPU NVIDIA GeForce GTX 1080 Ti
[C2] PASS env 171 (pydisort 1.7.1) full run 1: exit 1; 10 failed, 187 passed in 18.03s; abort: none
[S0] pyharp 2.7.8, pydisort 1.7.1, torch 2.10.0+cu128, Python 3.11.13
[H2] newest pydisort on PyPI: pydisort (1.8.13)
python 3.11.13, torch 2.10.0+cu126, numpy 2.4.6, pydisort 1.8.13, pyharp 2.7.8
pyharp source f34506f9d14ee7b1f2e1222775baa5093ae6967f, pydisort source 74f8d7e995545a686b04d503b6f81135af48d87c
[C3] PASS Toon SW f64 CUDA vs CPU: 4.235e-14 (tol <= 1.0e-12)
[F1] tests/spectra/test_hitemp_lines.py::test_prepare: 0 failed of 25 runs (temporary directory on tmpfs)
== check: 3 labels, 0 FAIL
"""
HOST_B = """versions: python 3.11.9, torch 2.10.0+cu128, numpy 2.4.7, pyharp 2.7.9.dev0+gf34506f9d.d20261026, pydisort 1.7.1; CUDA 12.8, Quadro RTX 4000
environment: pyharp source f34506f9d14ee7b1f2e1222775baa5093ae6967f; CPU Intel(R) Xeon(R), 12 logical; gcc 11.5.0
host: x86_64, 12 logical CPUs, torch default threads 6
[C1] INFO 1 thread(s), 50 layers, 256 columns: Toon SW: 7.3 us/column (1.0 x Toon SW)
[C13] INFO 6 thread(s), 50 layers, 256 columns: Toon SW: 2.9 us/column (1.0 x Toon SW)
[C14] INFO 6 thread(s), 50 layers, 256 columns: DISORT SW nstr=64: 2900.1 us/column (1000.0 x Toon SW)
env 171: environment: pyharp source f34506f9d14ee7b1f2e1222775baa5093ae6967f; GPU Quadro RTX 4000
[C2] PASS env 171 (pydisort 1.7.1) full run 1: exit 1; 10 failed, 187 passed in 9.81s; abort: none
[S0] pyharp 2.7.8, pydisort 1.7.1, torch 2.10.0+cu126, Python 3.11.9
[H2] newest pydisort on PyPI: pydisort (1.9.0)
python 3.11.9, torch 2.10.0+cu128, numpy 2.4.7, pydisort 1.8.13, pyharp 2.7.8
pyharp source f34506f9d14ee7b1f2e1222775baa5093ae6967f, pydisort source 74f8d7e995545a686b04d503b6f81135af48d87c
[C3] PASS Toon SW f64 CUDA vs CPU: 4.235e-14 (tol <= 1.0e-12)
[F1] tests/spectra/test_hitemp_lines.py::test_prepare: 0 failed of 25 runs (temporary directory on ext2/ext3)
== check: 3 labels, 0 FAIL
"""


def test_version_host_timing_and_date_lines_are_normalised(tmp_path):
    bad, out = run(tmp_path, HOST_A, HOST_B)
    assert bad == 0, out
    assert out.rstrip().endswith("chXX: REPRODUCED")


def test_the_normalised_form_keeps_the_label_verdict_and_configuration():
    lines = co.normalise(HOST_A)[0]
    assert "[C14] INFO <n> thread(s), 50 layers, 256 columns: DISORT SW nstr=64: <time> us/column (<ratio> x Toon SW)" \
        in lines
    assert "[C2] PASS env 171 (pydisort 1.7.1) full run 1: exit 1; 10 failed, 187 passed in <time>; abort: none" in lines
    assert "[S0] pyharp 2.7.8, pydisort 1.7.1, torch <ver>, Python <ver>" in lines
    assert not any(l.startswith(("versions:", "environment:", "host:", "env 171: environment:")) for l in lines)


# --- what still fails: any change in a check result -----------------------------------------------------------
@pytest.mark.parametrize("old,new", [
    ("4.235e-14 (tol", "4.236e-14 (tol"),                        # a check value
    ("[C3] PASS", "[C3] FAIL"),                                    # a verdict
    ("10 failed, 187 passed", "11 failed, 186 passed"),            # a test count
    ("3 labels, 0 FAIL", "3 labels, 1 FAIL"),                      # the summary
    ("exit 1; 10", "exit 0; 10"),                                   # an exit status recorded by a check
    ("50 layers, 256 columns: DISORT SW nstr=64", "50 layers, 256 columns: DISORT SW nstr=32"),  # a timing row's case
    ("pydisort 1.7.1, torch 2.10.0+cu128", "pydisort 1.8.13, torch 2.10.0+cu128"),  # the configuration under test
    ("0 failed of 25 runs", "1 failed of 25 runs"),               # the flaky-test count next to a host token
])
def test_a_changed_check_result_fails(tmp_path, old, new):
    assert old in HOST_A
    bad, out = run(tmp_path, HOST_A, HOST_A.replace(old, new, 1))
    assert bad == 1 and "chXX: NOT REPRODUCED" in out and "DIFFERS  x.out" in out


def test_a_dropped_or_added_line_fails(tmp_path):
    lines = HOST_A.splitlines(keepends=True)
    assert run(tmp_path, HOST_A, "".join(lines[:-2] + lines[-1:]))[0] == 1
    assert run(tmp_path, HOST_A, HOST_A + "[C4] INFO extra\n")[0] == 1


def test_a_missing_output_fails(tmp_path):
    (tmp_path / "e").mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / "e" / "x.out").write_text("[C1] PASS a\n")
    out = io.StringIO()
    assert co.compare("chXX", tmp_path / "e", tmp_path / "a", ["x.out"], stream=out) == 1
    assert "MISSING  x.out (not regenerated)" in out.getvalue()


def test_timing_masks_apply_only_on_timing_lines():
    assert co.normalise("[C1] INFO 16 thread(s), (2.0 x Toon SW) 4 layers")[0] == \
        ["[C1] INFO 16 thread(s), (2.0 x Toon SW) 4 layers"]


# --- without CUDA (ch09 on a GPU torch has no kernels for) ----------------------------------------------------
WITH_CUDA = """[C1] PASS Toon SW f64 batch vs per-column loop, CPU: 0.000e+00 (tol <= 1.0e-14)
[C2] PASS Toon SW f64 CUDA vs CPU: 4.235e-14 (tol <= 1.0e-12)
[C2] INFO Toon SW float32 floor, CPU float32 vs CPU float64: 1.283e-05 -> tolerance 2.57e-05
[C3] PASS Toon SW f32 batch vs per-column loop, CPU: 0.000e+00 (tol <= 1.0e-06)
[C4] INFO cell Toon SW|CUDA f64: pass (4.2e-14)
== check_ch09_batch_device: 4 labels, 0 FAIL
"""
WITHOUT_CUDA = """CUDA legs not run: torch 2.10.0+cu126 has no kernels for NVIDIA GeForce RTX 5090 (sm_120)
[C1] PASS Toon SW f64 batch vs per-column loop, CPU: 0.000e+00 (tol <= 1.0e-14)
[C2] PASS Toon SW f32 batch vs per-column loop, CPU: 0.000e+00 (tol <= 1.0e-06)
[C3] INFO cell Toon SW|CUDA f64: not run (torch 2.10.0+cu126 has no kernels for NVIDIA GeForce RTX 5090 (sm_120))
== check_ch09_batch_device: 3 labels, 0 FAIL
"""


def test_without_cuda_the_cpu_lines_are_compared_and_the_verdict_says_so(tmp_path):
    assert run(tmp_path, WITH_CUDA, WITHOUT_CUDA, exclude_cuda="r")[0] == 1      # the floor line is CUDA-only
    bad, out = run(tmp_path, WITH_CUDA, WITHOUT_CUDA, exclude_cuda="no kernels for sm_120",
                   cuda_lines=r"\bCUDA\b|float32 floor")
    assert bad == 0, out
    assert out.rstrip().endswith("chXX: REPRODUCED WITHOUT CUDA (CUDA legs not run: no kernels for sm_120)")
    assert run(tmp_path, WITH_CUDA, WITHOUT_CUDA)[0] == 1          # and never without the option


def test_without_cuda_a_changed_cpu_result_still_fails(tmp_path):
    changed = WITHOUT_CUDA.replace("[C2] PASS Toon SW f32 batch vs per-column loop, CPU: 0.000e+00",
                                   "[C2] PASS Toon SW f32 batch vs per-column loop, CPU: 1.000e-07")
    bad, out = run(tmp_path, WITH_CUDA, changed, exclude_cuda="x")
    assert bad == 1 and "NOT REPRODUCED" in out


def test_not_compared_files_are_named(tmp_path):
    (tmp_path / "e").mkdir()
    (tmp_path / "a").mkdir()
    out = io.StringIO()
    assert co.compare("ch09", tmp_path / "e", tmp_path / "a", ["d1.out"], stream=out, exclude_cuda="r",
                      not_compared={"d1.out"}) == 0
    assert "not compared  d1.out (needs the CUDA legs)" in out.getvalue()


def test_cli_exit_status(tmp_path):
    (tmp_path / "e").mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / "e" / "x.out").write_text("[C1] PASS 1.0\n")
    (tmp_path / "a" / "x.out").write_text("[C1] PASS 1.0\n")
    assert co.main(["chXX", str(tmp_path / "e"), str(tmp_path / "a"), "x.out"]) == 0
    (tmp_path / "a" / "x.out").write_text("[C1] PASS 1.1\n")
    assert co.main(["chXX", str(tmp_path / "e"), str(tmp_path / "a"), "x.out"]) == 1
    assert co.main(["chXX"]) == 2
    assert co.main(["--not-compared", "x.out", "chXX", "e", "a", "x.out"]) == 2   # only with --exclude-cuda


# --- declared host-dependent measurements (derivation-checks/host-dependent.json) ----------------------------
needs_declarations = pytest.mark.skipif(not HOST_DEPENDENT.exists(), reason="no derivation-checks/host-dependent.json")


def run_host(tmp_path, rel, expected, actual):
    (tmp_path / "e").mkdir(exist_ok=True)
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "e" / rel).write_text(expected)
    (tmp_path / "a" / rel).write_text(actual)
    out = io.StringIO()
    bad = co.compare("chXX", tmp_path / "e", tmp_path / "a", [rel], stream=out,
                     host_rules=co.load_host_dependent(HOST_DEPENDENT))
    return bad, out.getvalue()


@needs_declarations
def test_every_declaration_has_a_reason_and_evidence_and_matches_a_committed_line():
    import json
    spec = json.loads(HOST_DEPENDENT.read_text())["files"]
    for pattern, entries in spec.items():
        files = [p for p in CHECKS.glob(pattern)] or [p for p in CHECKS.parent.glob(pattern)]   # figure data in src/
        assert files, pattern
        lines = [l for f in files for l in co.read_output(f, f.name).splitlines()]   # a .json as the compare reads it
        for e in entries:
            assert e["why"] and e["evidence"], (pattern, e["lines"])
            rx = co.re.compile(e["lines"])
            assert any(rx.search(l) for l in lines), (pattern, e["lines"])


GPU = ("[C22] EXPECTED-FAIL DISORT SW f64 nstr=8 CUDA vs CPU, omega<1 columns: 8.291e-05 (defect present when > 1.0e-12)\n"
       "[C10] PASS Toon LW f64 batch vs per-column loop, CPU (bitwise-equal fraction 0.9821): 3.517e-16 (tol <= 1.0e-14)\n"
       "[C11] PASS Toon LW f64 batch vs per-wavelength loop, CPU: 0.000e+00 (tol <= 1.0e-14)\n"
       "[C75] INFO cell DISORT SW|CUDA f64: fail (omega<1/omega=1 by nstr 8: 8.3e-05/3.3e-10; fails at [8])\n")


@needs_declarations
def test_a_gpu_dependent_value_is_masked_but_its_verdict_and_tolerance_are_not(tmp_path):
    rel = "check_ch09_batch_device_pydisort1813.out"
    other = (GPU.replace("8.291e-05", "1.259e-04").replace("0.9821", "0.9971")
             .replace("8.3e-05/3.3e-10", "1.3e-04/2.9e-10"))
    bad, out = run_host(tmp_path, rel, GPU, other)
    assert bad == 0, out
    assert "3 line(s) with declared host-dependent values differ" in out
    assert "REPRODUCED (3 line(s) differ only in declared host-dependent values" in out


@needs_declarations
@pytest.mark.parametrize("old,new", [
    ("EXPECTED-FAIL DISORT SW f64 nstr=8", "FAIL DISORT SW f64 nstr=8"),     # the measurement crossed its tolerance
    ("defect present when > 1.0e-12", "defect present when > 1.0e-10"),   # the tolerance
    ("): 3.517e-16 (tol", "): 3.600e-16 (tol"),                            # the difference itself, not the fraction
    ("per-wavelength loop, CPU: 0.000e+00", "per-wavelength loop, CPU: 1.000e-16"),   # an undeclared CPU value
    ("fails at [8]", "fails at [8, 16]"),                                  # which stream counts fail
    ("cell DISORT SW|CUDA f64: fail", "cell DISORT SW|CUDA f64: pass"),
])
def test_what_a_host_dependent_line_still_compares(tmp_path, old, new):
    assert old in GPU
    assert run_host(tmp_path, "check_ch09_batch_device_pydisort171.out", GPU, GPU.replace(old, new, 1))[0] == 1


@needs_declarations
def test_roundoff_is_masked_only_below_1e_15(tmp_path):
    rel = "check_ch05_analytic.out"
    line = "[C1] PASS A albedo=0.0 Toon: max rel err of dn: {} (tol <= 1.0e-12)\n"
    assert run_host(tmp_path, rel, line.format("1.931e-16"), line.format("0.000e+00"))[0] == 0
    assert run_host(tmp_path, rel, line.format("1.931e-16"), line.format("3.000e-14"))[0] == 1
    other = "[C9] INFO A albedo=0.4 Toon: |up_TOA - A_s F_dir(tau0) 2E3(tau0)|/F_inc: {} (two-stream)\n"
    assert run_host(tmp_path, rel, other.format("6.248e-03"), other.format("6.249e-03"))[0] == 1


@needs_declarations
def test_d1_counts_and_abort_messages_are_chance_but_the_abort_is_not(tmp_path):
    rel = "check_ch09_d1.out"
    a = ("[C2] PASS env 171 (pydisort 1.7.1) full run 1: exit 1; 10 failed, 187 passed in 18.03s; abort: none\n"
         "[C14] EXPECTED-FAIL env 171b-1813-drift (pydisort 1.8.13) full run 1: exit 134; no summary; "
         "abort: corrupted size vs. prev_size\n"
         "[C1] PASS env 171 (pydisort 1.7.1) rayleigh run 1: exit 0; 2 passed in 3.22s; abort: none\n")
    b = (a.replace("10 failed, 187 passed in 18.03s", "9 failed, 188 passed in 9.1s")
         .replace("no summary", "9 failed, 188 passed in 7.0s").replace("corrupted size vs. prev_size", "free(): invalid pointer"))
    assert run_host(tmp_path, rel, a, b)[0] == 0
    for old, new in [("exit 134", "exit 1"), ("EXPECTED-FAIL env 171b", "FAIL env 171b"),
                     ("abort: corrupted size vs. prev_size", "abort: none"),
                     ("abort: none\n[C14]", "abort: double free\n[C14]"), ("2 passed in 3.22s", "1 passed in 3.22s")]:
        assert run_host(tmp_path, rel, a, a.replace(old, new, 1))[0] == 1, (old, new)


@needs_declarations
def test_declarations_apply_only_to_their_files(tmp_path):
    bad, _ = run_host(tmp_path, "ch08_config.pydisort-1.7.1.out", GPU, GPU.replace("8.291e-05", "1.259e-04"))
    assert bad == 1
