"""ch01 check: the quick start of chapter 1 runs as printed, and the sums of the band and column pipeline hold.

The quick start (book/chapters/01-overview/_quickstart.qmd) is a user script in three fenced python blocks, each
preceded by the comment `<!-- quickstart-code -->`; its printed output is the fenced block after
`<!-- quickstart-output -->`. This check reads those blocks from the chapter file, so the code it runs is the code the
reader sees.

  [C1] The three blocks, joined, run in a fresh directory with this interpreter; their stdout equals the output block
       of the chapter character for character.
  [C2] Optical-property assembly (eq-ch01-pipeline-prop), shortwave band of the quick start (an absorbing gas and a
       scattering haze with different cross sections): the two compiled opacities are loaded and run here, and the
       solver input `prop` of the band must hold dtau = dz sum_a k_a, omega = sum_a omega_a k_a / sum_a k_a and
       g = sum_a g_a omega_a k_a / sum_a omega_a k_a computed from them, to 1e-15 relative (two products and a
       quotient). The case must discriminate: the plain mean of the albedos and the mean with the two extinctions
       swapped must each differ from the weighted omega by more than 0.1, so an unweighted or mis-weighted mixing
       rule fails.
  [C3] Column sums (eq-ch01-pipeline-net): the net flux, the surface downward flux and the top upward flux that
       Radiation.forward returns equal the up - down, down[surface] and up[top] of the sum over bands of the
       `spectra` buffer, to 1e-14 relative to the largest band flux (one sum of two bands, then one difference).
  [C4] Weight mode (eq-ch01-pipeline-band): a shortwave band of two spectral points with different cross sections
       and weights (0.25, 0.75) returns sum_j w_j F_j of its `spectrum` buffer, to 1e-15 relative.
  [C5] Wavenumber mode (eq-ch01-pipeline-band): the same band on the wavenumber grid (10000, 12000, 20000) cm^-1
       returns the trapezoid rule over its `spectrum` buffer, to 1e-15 relative.
  [C7] Boundary values of the quick-start column: the shortwave downward flux at the top is mu0 F0 = 500 W m-2 and
       the longwave downward flux at the top is 0, to 1e-14 relative. The longwave upward flux at the black surface
       (`hard_surface`) is checked twice: (a) internally, against pi * bbflux_wavenumber(1, 3000, 300 K), pyharp's
       own band Planck function, to 1e-14 relative (the solver uses that function, so this shows the boundary
       condition, not the Planck function); (b) independently, against pi times the integral of B_nu from 1 to
       3000 cm-1 at 300 K by mpmath quadrature (30 digits) with the exact SI values of h, c and k, to 3e-5 relative:
       pyharp's series uses rounded c2 and sigma and six exponential terms, which put its band values within about
       1e-5 of the quadrature here (chapter 4, band Planck function); 3e-5 leaves a factor of three.
  [C6] A band with neither weights nor a wavenumber grid is refused when Radiation is built, with the message of
       RadiationBandImpl::reset ("Either 'wavenumber' or 'weight' must be set").

With --data FILE the band fluxes of the quick-start column (per band, upward and downward, at the 5 levels) are
written as CSV for the figure fig-ch01-quickstart-fluxes.

Needs torch and a pyharp built from source at the pin of code_pin.yml (derivation-checks/ch04/setup_env.sh).
Run:   python3 check_ch01_quickstart.py [--data FILE]   (any directory; exits with the number of failed claims)
Pins:  PYHARP_WT names the pyharp source tree; its commit is printed.
"""
import argparse
import math
import os
import platform
import re
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

import pyharp
import torch

torch.set_num_threads(1)
QMD = Path(__file__).resolve().parents[1] / "book" / "chapters" / "01-overview" / "_quickstart.qmd"


def blocks(marker):
    """Fenced blocks that follow `<!-- marker -->` in the chapter file, in order (text between the fences)."""
    text = QMD.read_text()
    return [m.group(1) for m in re.finditer(r"<!-- " + marker + r" -->\s*\n```[^\n]*\n(.*?)\n```", text, re.S)]


def bound(err, tol):
    """A round-off difference is reported against its tolerance, not by digits that differ between hosts."""
    return f"below {tol:.0e}" if err <= tol else f"{err:.1e}, above {tol:.0e}"


def report(n, ok, text):
    print(f"[C{n}] {'PASS' if ok else 'FAIL'} {text}")
    return bool(ok)


def git_head():
    path = os.environ.get("PYHARP_WT")
    if not path:
        return "unset"
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "not a git tree"


def check_C1(code, work):
    (work / "quickstart.py").write_text(code + "\n")
    r = subprocess.run([sys.executable, "-I", "quickstart.py"], cwd=work, capture_output=True, text=True)
    want = blocks("quickstart-output")
    ok = r.returncode == 0 and len(want) == 1 and r.stdout.rstrip("\n") == want[0].rstrip("\n")
    for line in r.stdout.rstrip("\n").split("\n"):
        print(f"     quick start: {line}")
    return report(1, ok, f"quick start ({len(code.splitlines())} lines in {len(blocks('quickstart-code'))} blocks) exit "
                  f"{r.returncode}; stdout equals the chapter's output block: {ok}")


def check_C2(ns, run_dir):
    """The band's solver input against the mixing rule computed here from the two compiled opacities themselves."""
    sw = ns["rad"].module("sw")
    prop = sw.buffer("prop")[0, 0]                      # (nlyr, nprop) of the one spectral point and column
    conc, dz = ns["conc"], ns["dz"]
    ops = [torch.jit.load(str(run_dir / f)) for f in ("gas_sw.pt", "haze_sw.pt")]
    out = [m(conc)[0, 0] for m in ops]                  # (nlyr, 3): extinction [1/m], albedo, asymmetry factor
    k = torch.stack([o[:, 0] for o in out])             # (nopacity, nlyr)
    w = torch.stack([o[:, 1] for o in out])
    g = torch.stack([o[:, 2] for o in out])
    weighted = (w * k).sum(0) / k.sum(0)                # eq-ch01-pipeline-prop
    plain = w.mean(0)                                   # the unweighted mean, a mutant
    swapped = (w * k.flip(0)).sum(0) / k.sum(0)         # each albedo weighted by the other opacity's extinction
    want = torch.stack([dz * k.sum(0), weighted, (g * w * k).sum(0) / (w * k).sum(0)], -1)
    err = ((prop[:, :3] - want).abs() / want.abs()).max().item()
    sep = min((weighted - plain).abs().min().item(), (weighted - swapped).abs().min().item())
    ok = err <= 1e-15 and sep > 0.1
    return report(2, ok, f"shortwave prop (dtau, omega, g) per layer " + ", ".join(f"{x:.6g}" for x in prop[0, :3].tolist())
                  + f"; mixing rule from the two opacities (k dz = "
                  + ", ".join(f"{x:.6g}" for x in (k[:, 0] * dz[0]).tolist()) + f"): omega {weighted[0].item():.6g}, relative difference "
                  f"{bound(err, 1e-15)}; the case discriminates: plain mean {plain[0].item():.6g}, swapped weights "
                  f"{swapped[0].item():.6g}, both more than 0.1 from the weighted value: {sep > 0.1}")


def check_C3(ns):
    rad = ns["rad"]
    total = rad.spectra.sum(0)                          # (ncol, nlev, 4), level 0 = surface
    net, surf, toa = ns["net"], ns["down_surface"], ns["up_toa"]
    scale = rad.spectra.abs().max().item()
    errs = [(net - (total[..., 0] - total[..., 1])).abs().max().item(),
            (surf - total[:, 0, 1]).abs().max().item(),
            (toa - total[:, -1, 0]).abs().max().item()]
    ok = max(errs) <= 1e-14 * scale
    return report(3, ok, f"{rad.spectra.shape[0]} bands; |difference| / largest band flux: net, surface and top "
                  f"{bound(max(errs) / scale, 1e-14)}")


SPECTRAL = '''
class Spectral(torch.nn.Module):
    def __init__(self, nwave: int):
        super().__init__()
        self.nwave = nwave
    def forward(self, conc: torch.Tensor) -> torch.Tensor:
        out = torch.zeros((self.nwave, conc.shape[0], conc.shape[1], 3), dtype=conc.dtype)
        for j in range(self.nwave):
            out[j, :, :, 0] = (0.5e-4 + 0.5e-4 * j) * conc[..., 0]
        out[..., 1].fill_(0.5)
        out[..., 2].fill_(0.6)
        return out
'''

YAML2 = """species: [{{name: gas, composition: {{H: 2}}}}]
geometry: {{cells: {{nx1: 4}}}}
opacities:
  spectral: {{type: jit, species: [gas], nmom: 1, data: [{pt}]}}
bands:
  - {{name: sw, range: [10000., 20000.], opacities: [spectral], solver: toon, nwave: {nwave}}}
"""


def spectral_band(work, nwave, setter):
    (work / "spectral_module.py").write_text("import torch\n" + SPECTRAL)
    ns = runpy.run_path(str(work / "spectral_module.py"), run_name="ch01_spectral")  # a file, so TorchScript can read the class source
    pt = str(work / f"spectral{nwave}.pt")
    pyharp.compile(ns["Spectral"](nwave), pt)
    (work / f"band{nwave}.yaml").write_text(YAML2.format(pt=pt, nwave=nwave))
    options = pyharp.RadiationOptions.from_yaml(str(work / f"band{nwave}.yaml"))
    setter(options.bands()[0])
    rad = pyharp.Radiation(options)
    conc, dz = torch.full((1, 4, 1), 40.0), torch.full((4,), 250.0)
    bc = {"sw/umu0": torch.tensor([0.5]), "sw/fbeam": torch.full((nwave, 1), 1000.0),  # (nwave, ncol)
          "sw/albedo": torch.full((nwave, 1), 0.2)}
    rad.forward(conc, dz, bc, {})
    band = rad.module("sw")
    return band.buffer("spectrum"), rad.spectra[0]


def check_C4(work):
    w = [0.25, 0.75]
    spec, out = spectral_band(work, 2, lambda b: b.weight(w))
    want = w[0] * spec[0] + w[1] * spec[1]
    err = ((out[..., :2] - want[..., :2]).abs().max() / want[..., :2].abs().max()).item()
    differ = (spec[0] - spec[1]).abs().max().item() > 0
    return report(4, err <= 1e-15 and differ, f"weights {w}: band flux minus sum_j w_j F_j, relative {bound(err, 1e-15)}; "
                  f"the two spectral points differ: {differ}")


def check_C5(work):
    nu = [10000.0, 12000.0, 20000.0]
    spec, out = spectral_band(work, 3, lambda b: b.wavenumber(nu))
    want = sum(0.5 * (nu[j + 1] - nu[j]) * (spec[j] + spec[j + 1]) for j in range(2))
    err = ((out[..., :2] - want[..., :2]).abs().max() / want[..., :2].abs().max()).item()
    return report(5, err <= 1e-15, f"wavenumbers {nu} cm-1: band flux minus the trapezoid rule, relative "
                  f"{bound(err, 1e-15)}")


def check_C6(work):
    (work / "nogrid.yaml").write_text(YAML2.format(pt=str(work / "spectral2.pt"), nwave=1))
    options = pyharp.RadiationOptions.from_yaml(str(work / "nogrid.yaml"))
    try:
        pyharp.Radiation(options)
        msg = "no error"
    except Exception as e:  # the binding raises a RuntimeError carrying the TORCH_CHECK message
        msg = str(e)
    ok = "Either 'wavenumber' or 'weight' must be set in band sw" in msg
    return report(6, ok, f"band without a spectral grid: refused with \"Either 'wavenumber' or 'weight' must be set in "
                  f"band sw\": {ok}")


def planck_band_quadrature(lo, hi, temp):
    """pi * integral of B_nu [W m-2 sr-1 (cm-1)-1] over [lo, hi] cm-1, exact SI h, c, k, 30 digits (independent of
    pyharp)."""
    import mpmath as mp
    with mp.workdps(30):
        h, c, k = mp.mpf("6.62607015e-34"), mp.mpf("299792458"), mp.mpf("1.380649e-23")
        b = lambda nu: 2 * h * c**2 * (100 * nu)**3 / mp.expm1(h * c * 100 * nu / (k * temp)) * 100
        return float(mp.pi * mp.quad(b, mp.linspace(lo, hi, 7)))


def check_C7(ns):
    sp = ns["rad"].spectra[:, 0]                        # (nband, nlev, 4), level 0 = surface
    pib = math.pi * pyharp.bbflux_wavenumber(1.0, 3000.0, torch.tensor([300.0], dtype=torch.float64)).item()
    quad = planck_band_quadrature(1, 3000, 300)
    up = sp[1, 0, 0].item()
    errs = [abs(sp[0, -1, 1].item() / 500.0 - 1), abs(sp[1, -1, 1].item()), abs(up / pib - 1)]
    indep = up / quad - 1
    ok = max(errs) <= 1e-14 and abs(indep) <= 3e-5
    return report(7, ok, f"shortwave down at the top {sp[0, -1, 1].item():.6f} (mu0 F0 = 500); longwave down at the top "
                  f"{sp[1, -1, 1].item():.1f}; longwave up at the surface {up:.6f}: (a) against pyharp's pi B = "
                  f"{pib:.6f}, relative differences {bound(max(errs), 1e-14)}; (b) against the independent quadrature "
                  f"{quad:.6f}, relative difference {indep:+.1e} (tol 3e-5)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=None)
    a = ap.parse_args()
    import pydisort
    print(f"versions: pyharp {pyharp.__version__}, torch {torch.__version__}, Python {platform.python_version()}, "
          f"pydisort {pydisort.__version__}")
    print(f"pyharp source {git_head()}")
    print("device: CPU, precision: float64, threads: 1")
    code = "\n".join(blocks("quickstart-code"))
    with tempfile.TemporaryDirectory(prefix="ch01_qs_") as tmp:
        work = Path(tmp)
        oks = [check_C1(code, work / "c1") if (work / "c1").mkdir() is None else False]
        cwd = os.getcwd()
        (work / "ns").mkdir()
        os.chdir(work / "ns")
        (work / "ns" / "quickstart.py").write_text(code + "\n")
        try:
            with open(os.devnull, "w") as null:
                old, sys.stdout = sys.stdout, null
                try:  # run from a file, so TorchScript can read the class source
                    ns = runpy.run_path(str(work / "ns" / "quickstart.py"), run_name="ch01_quickstart")
                finally:
                    sys.stdout = old
        finally:
            os.chdir(cwd)
        oks += [check_C2(ns, work / "ns"), check_C3(ns), check_C4(work), check_C5(work), check_C6(work), check_C7(ns)]
        if a.data:
            sp = ns["rad"].spectra[:, 0]                # (nband, nlev, 4)
            rows = ["level,sw_up,sw_down,lw_up,lw_down"]
            for k in range(sp.shape[1]):
                rows.append(f"{k},{sp[0, k, 0]:.6f},{sp[0, k, 1]:.6f},{sp[1, k, 0]:.6f},{sp[1, k, 1]:.6f}")
            Path(a.data).write_text("\n".join(rows) + "\n")
    print(f"check_ch01_quickstart: {sum(oks)} of {len(oks)} claims pass")
    return len(oks) - sum(oks)


if __name__ == "__main__":
    sys.exit(main())
