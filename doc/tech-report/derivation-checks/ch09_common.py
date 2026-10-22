"""Shared setup for the ch09 checks (GPU and batching).

The checks run against an installed pyharp built at the code pin (code_pin.yml) with `-DCUDA=ON`, in the Python
environment it was built in, with the pydisort it was built against. Every check prints a version line first and
then one `[Cn] PASS|FAIL|INFO|UNSUPPORTED|EXPECTED-FAIL <label>: <numbers>` line per claim; the exit status is the
number of FAIL lines.

Layout (pyharp at the pin): properties (nwave, ncol, nlyr, nprop) with layer 0 at the BOTTOM; Toon returns
(nwave, ncol, nlyr + 1, 4), DISORT (nwave, ncol, nlyr + 1, 2); channel 0 upward, channel 1 total downward flux.
"""

import math
import os
import platform

import numpy as np
import torch
import pyharp
import pydisort

DTYPES = {"f64": torch.float64, "f32": torch.float32}


def version_line():
    v = (f"versions: python {platform.python_version()}, torch {torch.__version__}, numpy {np.__version__}, "
         f"pyharp {getattr(pyharp, '__version__', '?')}, pydisort {pydisort.__version__}")
    if torch.cuda.is_available():
        v += f"; CUDA {torch.version.cuda}, {torch.cuda.get_device_name(0)}"
    else:
        v += "; no CUDA device"
    return v


# ---- the environment line every check prints second (self-contained rule) ------------------------------------
PYHARP_PIN = "f34506f9d14ee7b1f2e1222775baa5093ae6967f"
PYDISORT_TAG_COMMIT = {"1.7.1": "8af15242a265a60ea6fb51c29d48e6688a63ab67",     # tag v1.7.1, the code pin
                       "1.8.13": "74f8d7e995545a686b04d503b6f81135af48d87c"}    # tag v1.8.13, comparison only


def _first_line(cmd):
    import shutil
    import subprocess
    exe = shutil.which(cmd[0])
    if exe is None and cmd[0] == "nvcc" and os.environ.get("CUDA_HOME"):
        exe = os.path.join(os.environ["CUDA_HOME"], "bin", "nvcc")
    if exe is None or not os.path.exists(exe):
        return "not found"
    lines = subprocess.run([exe] + cmd[1:], capture_output=True, text=True).stdout.strip().splitlines()
    rel = [l for l in lines if "release" in l]
    return (rel or lines or ["?"])[-1]


def env_line():
    """pyharp and pydisort commits, torch build, CPU, GPU and the compilers on PATH (those that built pyharp when
    the run follows the chapter's setup script)."""
    cpu = platform.processor() or platform.machine()
    try:
        with open("/proc/cpuinfo") as f:
            cpu = next(l.split(":", 1)[1].strip() for l in f if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none visible"
    nvcc = _first_line(["nvcc", "--version"])
    nvcc = nvcc.split(",")[1].strip() if "release" in nvcc else nvcc
    return (f"environment: pyharp source {PYHARP_PIN}; pydisort {pydisort.__version__} tag commit "
            f"{PYDISORT_TAG_COMMIT.get(pydisort.__version__, 'unknown')}; torch {torch.__version__} (CUDA "
            f"{torch.version.cuda}); CPU {cpu}, {os.cpu_count()} logical; GPU {gpu}; gcc "
            f"{_first_line(['gcc', '-dumpfullversion'])}; nvcc {nvcc}")


def hg_moments(g, nmom):
    g = np.asarray(g, dtype=float)
    return np.stack([g ** (l + 1) for l in range(nmom)], axis=-1)


def t(a, dtype, device):
    return torch.as_tensor(np.ascontiguousarray(a), dtype=dtype, device=device)


def nd(a, b):
    """max |a - b| / max |b| over every entry: the normalised largest difference."""
    a, b = a.double().cpu(), b.double().cpu()
    den = b.abs().max().item()
    return (a - b).abs().max().item() / (den if den > 0 else 1.0)


def bitwise(a, b):
    return (a.cpu() == b.cpu()).double().mean().item()


def attempt(fn):
    """Run fn; return its value, or the first line of the error it raised (a string)."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - the message is the measurement
        return str(e).splitlines()[0][:160]


class Checker:
    def __init__(self):
        self.n = 0
        self.fails = 0

    def _label(self):
        self.n += 1
        return f"[C{self.n}]"

    def check(self, label, value, tol):
        ok = value <= tol and not math.isnan(value)
        self.fails += 0 if ok else 1
        print(f"{self._label()} {'PASS' if ok else 'FAIL'} {label}: {value:.3e} (tol <= {tol:.1e})", flush=True)
        return ok

    def expect_fail(self, label, value, tol):
        """A candidate defect the text records: EXPECTED-FAIL while value > tol; FAIL once it is gone."""
        present = value > tol
        self.fails += 0 if present else 1
        print(f"{self._label()} {'EXPECTED-FAIL' if present else 'FAIL'} {label}: {value:.3e} "
              f"(defect present when > {tol:.1e})", flush=True)
        return present

    def unsupported(self, label, msg):
        print(f"{self._label()} UNSUPPORTED {label}: {msg}", flush=True)

    def info(self, label, text):
        print(f"{self._label()} INFO {label}: {text}", flush=True)

    def done(self, name):
        print(f"== {name}: {self.n} labels, {self.fails} FAIL")
        return self.fails
