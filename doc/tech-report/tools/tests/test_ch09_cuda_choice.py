"""Tests of the ch09 CUDA leg on GPUs the pinned torch has no kernels for (sm_120 under torch 2.10.0+cu126):
derivation-checks/cuda_capability.py (skip or run) and the torch build ch09_setup.sh chooses.

The arch lists are the ones torch.cuda.get_arch_list() returns for the two wheels, measured on the installed builds.
Run from the report directory: `python3 -m pytest tools/tests`.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHECKS = Path(__file__).resolve().parent.parent.parent / "derivation-checks"
sys.path.insert(0, str(CHECKS))

import cuda_capability as cc  # noqa: E402

CU126 = ["sm_50", "sm_60", "sm_70", "sm_75", "sm_80", "sm_86", "sm_90"]               # torch 2.10.0+cu126
CU128 = ["sm_70", "sm_75", "sm_80", "sm_86", "sm_90", "sm_100", "sm_120"]             # torch 2.10.0+cu128


@pytest.mark.parametrize("cap,archs,runs", [
    ((12, 0), CU126, False),   # RTX 5090 under the pin: the case this exists for
    ((12, 0), CU128, True),    # the build ch09_setup.sh installs there
    ((7, 5), CU126, True),     # Quadro RTX 4000
    ((7, 5), CU128, True),
    ((6, 1), CU126, True),     # GTX 1080 Ti, the recorded runs: sm_60 SASS runs on sm_61
    ((6, 1), CU128, False),    # why cu128 is not the pin everywhere
    ((8, 9), CU126, True),     # Ada runs sm_86 SASS
    ((10, 0), CU126, False),
    ((12, 0), CU126 + ["compute_90"], True),   # PTX of a lower architecture is JIT-compiled
])
def test_skip_reason_follows_the_arch_list(cap, archs, runs):
    reason = cc.skip_reason(True, cap, archs, "GPU", "2.10.0")
    assert (reason is None) == runs
    if not runs:
        assert f"(sm_{cap[0]}{cap[1]})" in reason and ("it ships sm_50" in reason or "it ships sm_70" in reason)


def test_the_sm120_reason_names_the_remedy():
    r = cc.skip_reason(True, (12, 0), CU126, "NVIDIA GeForce RTX 5090", "2.10.0+cu126")
    assert r == ("torch 2.10.0+cu126 has no kernels for NVIDIA GeForce RTX 5090 (sm_120): it ships sm_50, sm_60, "
                 "sm_70, sm_75, sm_80, sm_86, sm_90; ch09_setup.sh installs torch 2.10.0+cu128, which has sm_120, "
                 "on such a host")


def test_no_device():
    assert cc.skip_reason(False, (0, 0), CU126) == "no CUDA device"


def test_a_caller_reason_wins(monkeypatch):
    pytest.importorskip("torch")
    monkeypatch.setenv("CUDA_SKIP_REASON", "decided upstream")
    assert cc.probe()[0] == "decided upstream"


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("cap,nvcc,mode,want", [
    ("12.0", "12.9", "cuda", "cu128"),
    ("12.0", "12.8", "cuda", "cu128"),
    ("12.0", "12.6", "cuda", "cu126"),    # pyharp's sm_120 kernels cannot be built: keep the pin, the run skips
    ("7.5", "12.9", "cuda", "cu126"),
    ("6.1", "12.6", "cuda", "cu126"),
    ("0", "12.9", "cuda", "cu126"),       # no GPU
    ("12.0", "12.9", "cpu", "cu126"),
])
def test_ch09_setup_chooses_the_torch_build(tmp_path, cap, nvcc, mode, want):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "nvcc").write_text(f"#!/bin/sh\necho 'Cuda compilation tools, release {nvcc}, V{nvcc}.0'\n")
    (fake / "nvcc").chmod(0o755)
    env = dict(os.environ, PATH=f"{fake}:{os.environ['PATH']}", GPU_CAPABILITY=cap, SETUP_DRY_RUN="1")
    env.pop("TORCH_CUDA", None)
    r = subprocess.run(["bash", str(CHECKS / "ch09_setup.sh"), str(tmp_path / "root"), "1.7.1", mode],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert f"torch 2.10.0+{want} (highest GPU compute capability: {cap})" in r.stdout
    assert ("note: a GPU of compute capability" in r.stdout) == (cap == "12.0" and mode == "cuda" and want == "cu126")
    assert not (tmp_path / "root").exists()
