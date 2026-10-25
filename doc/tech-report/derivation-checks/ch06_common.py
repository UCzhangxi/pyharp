"""Shared setup for the ch06 checks (opacity sources).

The checks run against an installed pyharp built from source at the code pin (code_pin.yml) by
derivation-checks/ch06_setup.sh, and the pydisort it was built against. Every check prints two header lines (the
versions that move the digits, then the environment line of the self-contained rule) and then one
`[Cn] PASS|FAIL|INFO|CANDIDATE <label>: <numbers>` line per claim; the exit status is the number of FAIL lines.

A difference that is pure round-off is printed against its tolerance ("below 1e-15"), not by its digits, so that the
claim lines are the same on every host and for both pydisort versions; the digits a figure needs go to the data
files under src/pyharp_report/ch06/data/ instead.
"""

import os
import platform
import shutil
import subprocess
import tempfile
import textwrap

import numpy as np
import torch
import pyharp
import pydisort

PYHARP_PIN = "f34506f9d14ee7b1f2e1222775baa5093ae6967f"
PYDISORT_TAG_COMMIT = {"1.7.1": "8af15242a265a60ea6fb51c29d48e6688a63ab67",     # tag v1.7.1, the code pin
                       "1.8.13": "74f8d7e995545a686b04d503b6f81135af48d87c"}    # tag v1.8.13, comparison only


def version_line():
    """The versions that move the digits; no paths. pyharp's local version part (a build date) is dropped."""
    v = (f"versions: python {platform.python_version()}, torch {torch.__version__}, numpy {np.__version__}, "
         f"pyharp {pyharp.__version__.split('+')[0]}, pydisort {pydisort.__version__}")
    try:
        import scipy
        import mpmath
        v += f", scipy {scipy.__version__}, mpmath {mpmath.__version__}"
    except ImportError:
        pass
    return v


def _first_line(cmd):
    exe = shutil.which(cmd[0])
    if exe is None and cmd[0] == "nvcc" and os.environ.get("CUDA_HOME"):
        exe = os.path.join(os.environ["CUDA_HOME"], "bin", "nvcc")
    if exe is None or not os.path.exists(exe):
        return "not found"
    lines = subprocess.run([exe] + cmd[1:], capture_output=True, text=True).stdout.strip().splitlines()
    rel = [line for line in lines if "release" in line]
    return (rel or lines or ["?"])[-1]


def env_line():
    """pyharp and pydisort commits, torch build, CPU, GPU and the compilers on PATH (those that built pyharp when
    the run follows the chapter's setup script)."""
    cpu = platform.processor() or platform.machine()
    try:
        with open("/proc/cpuinfo") as f:
            cpu = next(line.split(":", 1)[1].strip() for line in f if line.startswith("model name"))
    except (OSError, StopIteration):
        pass
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none visible"
    nvcc = _first_line(["nvcc", "--version"])
    nvcc = nvcc.split(",")[1].strip() if "release" in nvcc else nvcc
    return (f"environment: pyharp source {PYHARP_PIN}; pydisort {pydisort.__version__} tag commit "
            f"{PYDISORT_TAG_COMMIT.get(pydisort.__version__, 'unknown')}; torch {torch.__version__} (CUDA "
            f"{torch.version.cuda}); CPU {cpu}, {os.cpu_count()} logical; GPU {gpu}; gcc "
            f"{_first_line(['gcc', '-dumpfullversion'])}; nvcc {nvcc}")


def header():
    torch.set_num_threads(1)
    print(version_line())
    print(env_line())
    print("device: CPU, precision: float64, threads: 1")


def report(n, ok, text, kind=None):
    """One claim line. kind overrides PASS/FAIL for lines that record a measurement (INFO) or a reproduced
    defect (CANDIDATE); those never count as failures."""
    tag = kind or ("PASS" if ok else "FAIL")
    print(f"[C{n}] {tag} {text}")
    return True if kind else bool(ok)


def bound(err, tol):
    """A round-off difference reported against its tolerance, not by digits that differ between hosts."""
    return f"below {tol:.0e}" if err <= tol else f"{err:.1e}, above {tol:.0e}"


def t(x):
    return torch.as_tensor(np.asarray(x, dtype=float), dtype=torch.float64)


class Config:
    """A radiation YAML written to a temporary directory and read by pyharp.RadiationOptions.from_yaml.

    pyharp keeps one global species list, set by the last configuration read; every check therefore reads its own
    configuration right before it builds the modules that use it."""

    def __init__(self, text):
        self.dir = tempfile.mkdtemp(prefix="ch06_")
        self.path = os.path.join(self.dir, "radiation.yaml")
        with open(self.path, "w") as f:
            f.write(textwrap.dedent(text))
        self.options = pyharp.RadiationOptions.from_yaml(self.path)

    def band(self, i=0):
        return self.options.bands()[i]

    def opacity(self, name, band=0):
        return self.band(band).opacities()[name]

    def file(self, name):
        return os.path.join(self.dir, name)


def refusal(fn):
    """The first line of the message of the exception fn() raises, or None if it returns."""
    try:
        fn()
    except Exception as e:  # pyharp raises RuntimeError from TORCH_CHECK
        return str(e).strip().splitlines()[0]
    return None
