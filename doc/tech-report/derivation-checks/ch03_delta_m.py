"""ch03 check: the delta-M scaling (Wiscombe 1977) as cdisort applies it inside pydisort, and how
pyharp's moment count decides whether it runs.

cdisort has no delta-M switch: it scales whenever some layer has a nonzero moment at index nstr
(f = chi_nstr), and otherwise runs unscaled. The checks:

  [C1] sympy: the scaled layer keeps its absorption optical depth, (1 - omega') tau' = (1 - omega) tau,
       and its scaled moments start at chi*_0 = 1 (Wiscombe 1977 eqs. 14, 20a, 20b).
  [C2] the code is the formula: a delta-M run gives the same flup and total downward flux as a run
       with delta-M off (all moments >= nstr zero) on inputs scaled by hand with eqs. 14, 20a, 20b.
       Error: max |difference| / (mu0 F0) at the top and bottom levels. Tolerance 1e-12: the two runs
       differ only in the round-off of the scaling arithmetic.
  [C3] rfldir is the unscaled beam mu0 F0 exp(-tau/mu0) with delta-M on and off (tol 1e-14 relative,
       one exp() and one product).
  [C4] delta-M lowers the flux error against a 128-stream reference at 4, 8 and 16 streams for a
       Henyey-Greenstein g = 0.9 layer and the Garcia-Siewert cloud (tau 1 and 8, omega 0.99,
       mu0 0.5, F0 = pi, black surface). Printed: relative errors of the reflected flux and of the
       bottom total downward flux, on and off.
  [P1] CANDIDATE: through pyharp, a DISORT band whose opacity supplies fewer moments than nstr runs
       with no delta-M (pydisort zero-pads the moments, so chi_nstr = 0): its fluxes equal those of
       the same band with delta-M switched off, and differ from the band with nmom = nstr.

Needs: torch, numpy, sympy, pydisort, and (for [P1]) a pyharp built against that pydisort.
Run:   python ch03_delta_m.py [--work DIR]
Pins:  PYHARP_WT and PYDISORT_SRC name the source trees; their commits are printed.
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
import pydisort
import sympy as sp
import torch
from pydisort import Disort, DisortOptions, scattering_moments


def git_head(var):
    path = os.environ.get(var)
    if not path:
        return "unset"
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "not a git tree"


def run(dtau, ssa, moms, nstr, umu0=0.5, fbeam=math.pi):
    """one layer; moms = chi_1..chi_nmom; returns (rfldir, rfldn, flup) at top and bottom"""
    nmom = len(moms)
    op = DisortOptions().header("ch03").flags("usrtau,lamber,quiet,onlyfl")
    op.ds().nlyr, op.ds().nstr, op.ds().nmom = 1, nstr, nmom
    op.user_tau(np.array([0.0, dtau]))
    op.accur(0.0)
    ds = Disort(op)
    prop = torch.zeros((1, 1, 1, 2 + nmom), dtype=torch.float64)
    prop[0, 0, 0, 0] = dtau
    prop[0, 0, 0, 1] = ssa
    prop[0, 0, 0, 2:] = torch.as_tensor(moms, dtype=torch.float64)
    ds.forward(prop, umu0=torch.tensor([umu0], dtype=torch.float64),
               phi0=torch.zeros(1, dtype=torch.float64),
               fbeam=torch.tensor([[fbeam]], dtype=torch.float64),
               albedo=torch.zeros((1, 1), dtype=torch.float64))
    return ds.gather_flx()[0, 0, :, :3].numpy()  # rows: top, bottom; columns rfldir, rfldn, flup


def check_c1():
    om, tau, f = sp.symbols("omega tau f", positive=True)
    omp = (1 - f) * om / (1 - om * f)       # W77 eq. 20b
    taup = (1 - om * f) * tau               # W77 eq. 20a
    chi0 = (1 - f) / (1 - f)                # W77 eq. 14 with chi_0 = 1
    ok = sp.simplify((1 - omp) * taup - (1 - om) * tau) == 0 and sp.simplify(chi0 - 1) == 0
    print(f"[C1] {'PASS' if ok else 'FAIL'} sympy: (1 - omega') tau' - (1 - omega) tau = 0 and chi*_0 = 1")
    return ok


def check_c2_c3():
    worst2 = worst3 = 0.0
    cases = 0
    for phase, gg in (("henyey-greenstein", 0.9), ("cloud-garcia-siewert", 0.0)):
        for tau in (1.0, 8.0):
            for nstr in (4, 8, 16):
                ssa = 0.99
                moms = scattering_moments(256, phase, gg).numpy()
                on = run(tau, ssa, moms, nstr)
                f = moms[nstr - 1]                                  # chi_nstr (moms[0] is chi_1)
                taup, ssap = (1 - ssa * f) * tau, (1 - f) * ssa / (1 - ssa * f)
                scaled = np.zeros(nstr)
                scaled[:nstr - 1] = (moms[:nstr - 1] - f) / (1 - f)  # chi*_1..chi*_{nstr-1}; chi*_nstr = 0
                off = run(taup, ssap, scaled, nstr)
                tot_on, tot_off = on[:, 0] + on[:, 1], off[:, 0] + off[:, 1]
                mu0f0 = 0.5 * math.pi
                worst2 = max(worst2, float(np.max(np.abs(tot_on - tot_off))) / mu0f0,
                             float(np.max(np.abs(on[:, 2] - off[:, 2]))) / mu0f0)
                ref = 0.5 * math.pi * math.exp(-tau / 0.5)
                zero = moms.copy()
                zero[nstr - 1:] = 0.0
                for r in (on, run(tau, ssa, zero, nstr)):
                    worst3 = max(worst3, abs(r[1, 0] / ref - 1))
                cases += 1
    ok2, ok3 = worst2 <= 1e-12, worst3 <= 1e-14
    print(f"[C2] {'PASS' if ok2 else 'FAIL'} delta-M run vs unscaled run on hand-scaled inputs: max |dF|/(mu0 F0) "
          f"{worst2:.1e} in flup and total downward flux (tol 1e-12; {cases} cases)")
    print(f"[C3] {'PASS' if ok3 else 'FAIL'} rfldir at the bottom = unscaled beam, delta-M on and off: max rel "
          f"dev {worst3:.1e} (tol 1e-14)")
    return ok2 and ok3


def check_c4():
    ok = True
    print(f"{'phase':22} {'tau':>4} {'nstr':>4} {'R on':>9} {'R off':>9} {'T on':>9} {'T off':>9}")
    for phase, gg in (("henyey-greenstein", 0.9), ("cloud-garcia-siewert", 0.0)):
        for tau in (1.0, 8.0):
            moms = scattering_moments(256, phase, gg).numpy()
            ref = run(tau, 0.99, moms, 128)
            r_up, r_dn = ref[0, 2], ref[1, 0] + ref[1, 1]
            for nstr in (4, 8, 16):
                on = run(tau, 0.99, moms, nstr)
                zero = moms.copy()
                zero[nstr - 1:] = 0.0
                off = run(tau, 0.99, zero, nstr)
                e = [(x[0, 2] - r_up) / r_up for x in (on, off)] + \
                    [(x[1, 0] + x[1, 1] - r_dn) / r_dn for x in (on, off)]
                print(f"{phase:22} {tau:4g} {nstr:4d} {e[0]:+9.1e} {e[1]:+9.1e} {e[2]:+9.1e} {e[3]:+9.1e}")
                ok &= max(abs(e[0]), abs(e[2])) < max(abs(e[1]), abs(e[3]))
    print(f"[C4] {'PASS' if ok else 'FAIL'} delta-M lowers the larger of the two flux errors in every case "
          "(R: reflected flux, T: bottom total downward flux, relative to 128 streams)")
    return ok


PYHARP_YAML = """species:
  - name: X
    composition: {{H: 2}}
geometry:
  cells:
    nx1: 4
opacities:
  cloud:
    type: jit
    species: [X]
    nmom: {nmom}
    data: [{pt}]
bands:
  - name: sw
    range: [10000.0, 20000.0]
    opacities: [cloud]
    solver: disort
    nwave: 1
    nstr: 4
    flags: lamber,quiet,onlyfl
"""


def check_p1(work):
    import pyharp

    class HG(torch.nn.Module):
        def __init__(self, nmom: int, nzero: int):
            super().__init__()
            self.nmom = nmom
            self.nzero = nzero  # moments from this 1-based index on are set to zero

        def forward(self, conc: torch.Tensor) -> torch.Tensor:
            out = torch.zeros((1, conc.shape[0], conc.shape[1], 2 + self.nmom), dtype=torch.float64)
            out[..., 0].fill_(1.0e-3)   # extinction [1/m]: tau = 1 over 1000 m
            out[..., 1].fill_(0.99)
            for m in range(1, self.nmom + 1):
                if m < self.nzero:
                    out[..., 1 + m].fill_(0.9 ** m)
            return out

    res = {}
    for lab, nmom, nzero in (("nmom 3 < nstr 4", 3, 99), ("nmom 4, chi_4 = 0", 4, 4), ("nmom 4 = nstr", 4, 99)):
        pt = os.path.join(work, f"hg_{nmom}_{nzero}.pt")
        pyharp.compile(HG(nmom, nzero), pt)
        yp = os.path.join(work, f"hg_{nmom}_{nzero}.yaml")
        with open(yp, "w") as fh:
            fh.write(PYHARP_YAML.format(nmom=nmom, pt=pt))
        bo = pyharp.RadiationOptions.from_yaml(yp).bands()[0]
        bo.weight([1.0])
        band = pyharp.RadiationBand(bo)
        flx = band.forward(torch.ones((1, 4, 1), dtype=torch.float64), torch.full((4,), 250.0, dtype=torch.float64),
                           {"sw/umu0": torch.tensor([0.5], dtype=torch.float64),
                            "sw/fbeam": torch.tensor([[1.0]], dtype=torch.float64),
                            "sw/albedo": torch.zeros((1, 1), dtype=torch.float64)},
                           {"tempf": torch.full((1, 5), 250.0, dtype=torch.float64)})
        res[lab] = flx[0, :, :2]
    same = bool(torch.equal(res["nmom 3 < nstr 4"], res["nmom 4, chi_4 = 0"]))
    d = ((res["nmom 3 < nstr 4"] - res["nmom 4 = nstr"]).abs().max() / 0.5).item()
    up3, up4 = res["nmom 3 < nstr 4"][-1, 0].item(), res["nmom 4 = nstr"][-1, 0].item()
    print(f"[P1] CANDIDATE {'reproduced' if same and d > 0 else 'not reproduced'}: pyharp band nstr 4, HG g 0.9, "
          f"tau 1, omega 0.99, mu0 0.5: opacity nmom 3 gives fluxes bitwise equal to delta-M off: {same}; "
          f"max |dF|/(mu0 F0) against nmom 4 = {d:.2e}; top F_up {up3:.5f} (nmom 3) vs {up4:.5f} (nmom 4)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="ch03_deltam_")
    os.makedirs(work, exist_ok=True)
    torch.set_num_threads(1)
    print(f"python {sys.version.split()[0]}, torch {torch.__version__}, numpy {np.__version__}, "
          f"sympy {sp.__version__}, pydisort {pydisort.__version__}")
    print(f"pyharp source {git_head('PYHARP_WT')}, pydisort source {git_head('PYDISORT_SRC')}")
    nfail = (not check_c1()) + (not check_c2_c3()) + (not check_c4())
    check_p1(work)
    sys.exit(nfail)


if __name__ == "__main__":
    main()
