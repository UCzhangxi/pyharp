"""ch03 check: grey, non-scattering, isothermal slab through pyharp RadiationBand + DISORT
(weight mode, one g-point of weight 1) against the analytic exponential-integral solution.

Setup: slab at temperature T over a black surface at Ts, no radiation incident at the top,
band [wmin, wmax] cm^-1, flags lamber,quiet,onlyfl,planck. With Bbar = int B_nu dnu over the band,

    F_up(top)    = pi Bbar(T) (1 - 2 E3(tau)) + 2 E3(tau) pi Bbar(Ts)
    F_dn(bottom) = pi Bbar(T) (1 - 2 E3(tau))

The deviation reported per stream count is the largest relative deviation of the two fluxes over
the optical-depth grid.

Labels:
  [C1] 32-stream maximum relative deviation <= 2e-4 (the acceptance value of the report outline)
  [C2] the maximum relative deviation falls monotonically with the stream count 4, 8, 16, 32
  [C3] in the opaque limit (tau >= 3) the deviation no longer depends on the quadrature: the 16- and
       32-stream deviations agree to 1e-7 (2 % of the floor) and stay below 5e-6; the value left is
       the band-integrated Planck function's own error (ch03_disotest.py prints it, label [C5])
  [C4] the floor of [C3] is reached by 16 and 32 streams only: at tau = 3 the 4- and 8-stream deviations
       (larger of up and down) are both above 2 x the 32-stream value there, i.e. still set by the quadrature

Needs: torch, numpy, scipy, pydisort and a pyharp built against that pydisort.
Run:   python ch03_e3_slab.py [--work DIR]      (default: a fresh temporary directory)
Pins:  set PYHARP_WT and PYDISORT_SRC to the source trees the packages were built from; their
       commits are printed (git rev-parse HEAD) so the output records what was run.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import pydisort
import pyharp
import scipy
import torch
from scipy.integrate import quad
from scipy.special import expn

H, C, KB = 6.62607015e-34, 2.99792458e8, 1.380649e-23  # CODATA 2018, exact


def git_head(var):
    path = os.environ.get(var)
    if not path:
        return "unset"
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "not a git tree"


def print_versions():
    print(f"python {sys.version.split()[0]}, torch {torch.__version__}, numpy {np.__version__}, "
          f"scipy {scipy.__version__}, pydisort {pydisort.__version__}")
    print(f"pyharp source {git_head('PYHARP_WT')}, pydisort source {git_head('PYDISORT_SRC')}")


def pi_planck(nu_cm, temp):
    """pi B_nu in W m^-2 (cm^-1)^-1"""
    nu = nu_cm * 100.0
    return np.pi * 2 * H * C**2 * nu**3 / np.expm1(H * C * nu / (KB * temp)) * 100.0


class Grey(torch.nn.Module):
    def __init__(self, k: float):
        super().__init__()
        self.k = k

    def forward(self, conc: torch.Tensor) -> torch.Tensor:
        out = torch.zeros((1, conc.shape[0], conc.shape[1], 2), dtype=torch.float64)
        # fill_ keeps float64: under torch.jit.script, "out[..., 0] = self.k" rounds k to float32
        out[..., 0].fill_(self.k)  # extinction [1/m]; column 1 (single-scattering albedo) stays 0
        return out


YAML = """species:
  - name: X
    composition: {{H: 2}}
geometry:
  cells:
    nx1: {nlyr}
opacities:
  grey:
    type: jit
    species: [X]
    data: [{pt}]
bands:
  - name: lw
    range: [{wmin}, {wmax}]
    opacities: [grey]
    solver: disort
    nwave: 1
    nstr: {nstr}
    flags: lamber,quiet,onlyfl,planck
"""


def run(work, tau, nstr, nlyr=4, wmin=500.0, wmax=700.0, temp=300.0, tsurf=250.0, ztot=1000.0):
    pt = os.path.join(work, f"grey_{tau}.pt")
    pyharp.compile(Grey(tau / ztot), pt)
    yp = os.path.join(work, f"band_{nstr}_{tau}.yaml")
    with open(yp, "w") as f:
        f.write(YAML.format(nlyr=nlyr, pt=pt, wmin=wmin, wmax=wmax, nstr=nstr))
    bo = pyharp.RadiationOptions.from_yaml(yp).bands()[0]
    bo.weight([1.0])
    pyharp.disort_config(bo.disort(), nstr, nlyr, 1, 1)
    band = pyharp.RadiationBand(bo)
    conc = torch.ones((1, nlyr, 1), dtype=torch.float64)
    dz = torch.full((nlyr,), ztot / nlyr, dtype=torch.float64)
    bc = {"lw/albedo": torch.zeros((1, 1), dtype=torch.float64),
          "btemp": torch.tensor([tsurf], dtype=torch.float64)}
    flx = band.forward(conc, dz, bc, {"tempf": torch.full((1, nlyr + 1), temp, dtype=torch.float64)})
    bt = quad(pi_planck, wmin, wmax, args=(temp,), epsabs=0, epsrel=1e-13)[0]
    bs = quad(pi_planck, wmin, wmax, args=(tsurf,), epsabs=0, epsrel=1e-13)[0]
    e3 = expn(3, tau)
    up_ref, dn_ref = bt * (1 - 2 * e3) + 2 * e3 * bs, bt * (1 - 2 * e3)
    # flx[col, level, channel]: level 0 is the bottom (pyharp arrays run bottom to top), channel 0 up, 1 down
    up, dn = flx[0, -1, 0].item(), flx[0, 0, 1].item()
    return dict(tau=tau, nstr=nstr, up=up, up_ref=up_ref, dn=dn, dn_ref=dn_ref,
                rel_up=abs(up / up_ref - 1), rel_dn=abs(dn / dn_ref - 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="ch03_e3_")
    os.makedirs(work, exist_ok=True)
    torch.set_num_threads(1)
    print_versions()
    nstrs, taus = [4, 8, 16, 32], [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
    rows = [run(work, t, n) for n in nstrs for t in taus]
    print(f"{'nstr':>4} {'tau':>6} {'F_up(top)':>12} {'reference':>12} {'rel':>8} "
          f"{'F_dn(bot)':>12} {'reference':>12} {'rel':>8}")
    for r in rows:
        print(f"{r['nstr']:4d} {r['tau']:6g} {r['up']:12.5e} {r['up_ref']:12.5e} {r['rel_up']:8.1e} "
              f"{r['dn']:12.5e} {r['dn_ref']:12.5e} {r['rel_dn']:8.1e}")
    worst = {n: max(max(r["rel_up"], r["rel_dn"]) for r in rows if r["nstr"] == n) for n in nstrs}
    nfail = 0
    ok = worst[32] <= 2e-4
    nfail += not ok
    print(f"[C1] {'PASS' if ok else 'FAIL'} E3 slab, 32 streams: max rel dev {worst[32]:.2e} (tol 2e-4)")
    ok = all(worst[a_] > worst[b_] for a_, b_ in zip(nstrs, nstrs[1:]))
    nfail += not ok
    print(f"[C2] {'PASS' if ok else 'FAIL'} max rel dev falls with streams: "
          + ", ".join(f"{n}: {worst[n]:.2e}" for n in nstrs))
    thick = [r for r in rows if r["tau"] >= 3.0]
    d16 = {r["tau"]: max(r["rel_up"], r["rel_dn"]) for r in thick if r["nstr"] == 16}
    d32 = {r["tau"]: max(r["rel_up"], r["rel_dn"]) for r in thick if r["nstr"] == 32}
    same = max(abs(d16[t] - d32[t]) for t in d32)
    ok = same <= 1e-7 and max(d32.values()) < 5e-6
    nfail += not ok
    print(f"[C3] {'PASS' if ok else 'FAIL'} opaque limit tau >= 3: 32-stream max rel dev "
          f"{max(d32.values()):.2e} (tol 5e-6), |16 - 32 stream| = {same:.1e} (tol 1e-7)")
    at3 = {r["nstr"]: max(r["rel_up"], r["rel_dn"]) for r in thick if r["tau"] == 3.0}
    ok = all(at3[n] > 2 * at3[32] for n in (4, 8))
    nfail += not ok
    print(f"[C4] {'PASS' if ok else 'FAIL'} floor reached at 16 and 32 streams only: tau = 3 max rel dev "
          + ", ".join(f"{n}: {at3[n]:.1e}" for n in nstrs) + " (4 and 8 must exceed 2 x the 32-stream value)")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
