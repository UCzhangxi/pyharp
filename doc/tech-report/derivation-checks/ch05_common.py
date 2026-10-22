"""Shared setup for the ch05 checks (solver comparison and accuracy).

The checks run against an installed pyharp built at the code pin (code_pin.yml) and the pydisort it was built
against; the Python environment that runs them must be the one pyharp was built in. Every check prints a version
line first and then one `[Cn] PASS|FAIL|INFO <label>: <numbers>` line per claim; the exit status is the number of
FAIL lines.

Conventions (pyharp at the pin; see the ch05 text): pyharp and pydisort with `upward(True)` index layers and levels
from the BOTTOM (index 0 next to the surface). The helpers below take arrays top-down, as the test problems are
written, and flip them. Output channel 0 is the upward flux F^+; channel 1 is the total downward flux F^- + F_dir
for both solvers. Toon returns two more channels (layer midpoints) that these checks do not use.
"""

import itertools
import math
import os
import platform
import time

import numpy as np
import torch
import pyharp
import pydisort

SW_FLAGS = "lamber,quiet,onlyfl"
LW_FLAGS = "lamber,quiet,onlyfl,planck"

# ---- the ch05 grid: homogeneous slabs, Henyey-Greenstein phase function ----------------------------------------
TAU = [0.01, 0.1, 0.3, 1.0, 3.0, 10.0]
SSA_SW = [0.3, 0.6, 0.9, 0.99, 0.999, 1.0]
SSA_LW = [0.0, 0.3, 0.6, 0.9, 0.99]
G = [0.0, 0.5, 0.75, 0.85]
MU0 = [0.2, 0.5, 1.0]
ALBEDO = [0.0, 0.4]
NLYR_SW = 2                 # levels: top, middle, surface
NLYR_LW = 8                 # resolves the linear-in-tau temperature profile
T_TOP, T_BOT = 200.0, 300.0
WAVE_LO, WAVE_HI = 500.0, 1000.0   # thermal band [cm^-1]


def version_line():
    """The versions that move the digits; no paths."""
    v = (f"versions: python {platform.python_version()}, torch {torch.__version__}, numpy {np.__version__}, "
         f"pyharp {getattr(pyharp, '__version__', '?')}, pydisort {pydisort.__version__}")
    try:
        import scipy
        import mpmath
        v += f", scipy {scipy.__version__}, mpmath {mpmath.__version__}"
    except ImportError:
        pass
    if torch.cuda.is_available():
        v += f"; CUDA {torch.version.cuda}, {torch.cuda.get_device_name(0)}"
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


def sw_grid():
    a = np.array(list(itertools.product(TAU, SSA_SW, G, MU0, ALBEDO)), dtype=float)
    return {k: a[:, i] for i, k in enumerate(["tau", "ssa", "g", "mu0", "albedo"])}


def lw_grid():
    a = np.array(list(itertools.product(TAU, SSA_LW, G, ALBEDO)), dtype=float)
    return {k: a[:, i] for i, k in enumerate(["tau", "ssa", "g", "albedo"])}


def layers(total, nlyr):
    """(ncol,) totals -> (ncol, nlyr) equal layer values (top-down)."""
    return np.repeat(np.asarray(total, float)[:, None] / nlyr, nlyr, axis=1)


def same(value, nlyr):
    return np.repeat(np.asarray(value, float)[:, None], nlyr, axis=1)


def lw_temf(ncol):
    """Level temperatures, top-down, linear in optical-depth fraction from T_TOP to T_BOT."""
    frac = np.linspace(0.0, 1.0, NLYR_LW + 1)
    return np.repeat((T_TOP + (T_BOT - T_TOP) * frac)[None, :], ncol, axis=0)


# ---- solvers -----------------------------------------------------------------------------------------------------
def hg_moments(g, nmom):
    """Henyey-Greenstein Legendre moments chi_l = g**l, l = 1..nmom (the DISORT `pmom` after chi_0 = 1)."""
    g = np.asarray(g, dtype=float)
    return np.stack([g ** (l + 1) for l in range(nmom)], axis=-1)


def make_disort(nstr, nlyr, ncol, nwave=1, planck=False, wave_lower=None, wave_upper=None):
    op = pydisort.DisortOptions()
    op.upward(True)
    op.flags(LW_FLAGS if planck else SW_FLAGS)
    if wave_lower is not None:
        op.wave_lower(list(wave_lower))
        op.wave_upper(list(wave_upper))
    pyharp.disort_config(op, nstr, nlyr, ncol, nwave)   # nmom = nphase = nstr
    return pydisort.Disort(op)


def make_toon(planck=False, wave_lower=(1.0,), wave_upper=(2.0,), extra_flags=()):
    op = pyharp.ToonMcKay89Options()
    op.wave_lower(list(wave_lower))
    op.wave_upper(list(wave_upper))
    flags = (["planck"] if planck else []) + list(extra_flags)
    if flags:
        op.flags(",".join(flags))
    return pyharp.ToonMcKay89(op)


def _t(x, dtype=torch.float64, device="cpu"):
    return torch.as_tensor(np.ascontiguousarray(x), dtype=dtype, device=device)


def _prop(tau, ssa, extra):
    """Top-down (ncol, nlyr) arrays -> bottom-up (1, ncol, nlyr, 2 + nextra) property tensor."""
    ncol, nlyr = tau.shape
    prop = np.zeros((1, ncol, nlyr, 2 + extra.shape[-1]))
    prop[0, :, :, 0] = tau[:, ::-1]
    prop[0, :, :, 1] = ssa[:, ::-1]
    prop[0, :, :, 2:] = extra[:, ::-1, :]
    return prop


def run_disort_sw(nstr, tau, ssa, pmom, umu0, albedo, fbeam=1.0, dtype=torch.float64, device="cpu"):
    """Shortwave DISORT, one wavelength. Returns numpy (ncol, nlvl, 2), levels bottom-up."""
    tau = np.atleast_2d(tau)
    ncol, nlyr = tau.shape
    ds = make_disort(nstr, nlyr, ncol)
    bc = {"fbeam": _t(np.full((1, ncol), fbeam), dtype, device), "umu0": _t(umu0, dtype, device),
          "albedo": _t(np.reshape(albedo, (1, ncol)), dtype, device)}
    out = ds(_t(_prop(tau, ssa, pmom), dtype, device), **bc)
    return out[0, :, :, :2].double().cpu().numpy()


def run_disort_lw(nstr, tau, ssa, pmom, temf, albedo, wave_lower, wave_upper, dtype=torch.float64, device="cpu"):
    """Thermal DISORT, one band; temf (ncol, nlvl) top-down. Lambertian surface of emissivity 1 - albedo at the
    bottom-level temperature; no incoming radiation at the top (ttemp = temis = 0)."""
    tau = np.atleast_2d(tau)
    ncol, nlyr = tau.shape
    ds = make_disort(nstr, nlyr, ncol, planck=True, wave_lower=[wave_lower], wave_upper=[wave_upper])
    bc = {"albedo": _t(np.reshape(albedo, (1, ncol)), dtype, device), "temis": _t(np.zeros((1, ncol)), dtype, device),
          "btemp": _t(temf[:, -1], dtype, device), "ttemp": _t(np.zeros(ncol), dtype, device)}
    out = ds(_t(_prop(tau, ssa, pmom), dtype, device), temf=_t(temf[:, ::-1], dtype, device), **bc)
    return out[0, :, :, :2].double().cpu().numpy()


def run_toon_sw(tau, ssa, g, umu0, albedo, fbeam=1.0, dtype=torch.float64, device="cpu", toon=None):
    """Toon89 shortwave; g (ncol, nlyr) top-down. Same layout as run_disort_sw."""
    tau = np.atleast_2d(tau)
    ncol, _ = tau.shape
    toon = toon or make_toon()
    bc = {"fbeam": _t(np.full((1, ncol), fbeam), dtype, device), "umu0": _t(umu0, dtype, device),
          "albedo": _t(np.reshape(albedo, (1, ncol)), dtype, device)}
    out = toon(_t(_prop(tau, ssa, g[..., None]), dtype, device), **bc)
    return out[0, :, :, :2].double().cpu().numpy()


def run_toon_lw(tau, ssa, g, temf, albedo, wave_lower, wave_upper, dtype=torch.float64, device="cpu",
                extra_flags=("hard_surface",), toon=None):
    """Toon89 longwave (source-function technique), one band. `hard_surface` gives the surface emission
    (1 - albedo) B(T_bottom), the boundary DISORT uses; top_emission_flag stays 0 (no incoming radiation)."""
    tau = np.atleast_2d(tau)
    toon = toon or make_toon(planck=True, wave_lower=(wave_lower,), wave_upper=(wave_upper,),
                             extra_flags=extra_flags)
    out = toon(_t(_prop(tau, ssa, g[..., None]), dtype, device), temf=_t(temf[:, ::-1], dtype, device),
               albedo=_t(np.reshape(albedo, (1, tau.shape[0])), dtype, device))
    return out[0, :, :, :2].double().cpu().numpy()


def band_planck_flux(temp, wave_lower, wave_upper):
    """pi B integrated over the band [W m^-2]. pyharp.bbflux_wavenumber returns the band-integrated Planck
    radiance B [W m^-2 sr^-1]; the hemispheric flux of a black surface is pi times it."""
    t = torch.tensor([[float(temp)]], dtype=torch.float64)
    lo = torch.tensor([float(wave_lower)], dtype=torch.float64).view(1, 1, 1)
    hi = torch.tensor([float(wave_upper)], dtype=torch.float64).view(1, 1, 1)
    return math.pi * float(pyharp.bbflux_wavenumber(lo, hi, t).flatten()[0])


def timed(fn, repeat=3):
    best, res = float("inf"), None
    for _ in range(repeat):
        t0 = time.perf_counter()
        res = fn()
        best = min(best, time.perf_counter() - t0)
    return best, res


class Checker:
    """Numbers the claims [C1], [C2], ...; PASS/FAIL against a stated tolerance, INFO for measurements."""

    def __init__(self):
        self.n = 0
        self.fails = 0

    def _label(self):
        self.n += 1
        return f"[C{self.n}]"

    def check(self, label, value, tol, cmp="<="):
        ok = (value <= tol) if cmp == "<=" else (value >= tol)
        ok = ok and not (isinstance(value, float) and math.isnan(value))
        self.fails += 0 if ok else 1
        print(f"{self._label()} {'PASS' if ok else 'FAIL'} {label}: {value:.3e} (tol {cmp} {tol:.1e})", flush=True)
        return ok

    def expect_fail(self, label, value, tol):
        """A defect the text records: PASS means the defect is still present (value > tol)."""
        present = value > tol
        print(f"{self._label()} {'EXPECTED-FAIL' if present else 'FAIL'} {label}: {value:.3e} (defect present "
              f"when > {tol:.1e})", flush=True)
        self.fails += 0 if present else 1
        return present

    def info(self, label, text):
        print(f"{self._label()} INFO {label}: {text}", flush=True)

    def done(self, name):
        print(f"== {name}: {self.n} labels, {self.fails} FAIL")
        return self.fails
