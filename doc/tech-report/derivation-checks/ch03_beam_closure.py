"""ch03 check: direct beam (Beer-Lambert) and energy closure under conservative scattering, through
pyharp RadiationBand + DISORT (weight mode, one g-point of weight 1) and through pydisort directly.

(a) Beer-Lambert. Purely absorbing slab (omega = 0), beam of intensity F0 = 1 at cosine mu0, black
    surface: F_dn(tau) = mu0 F0 exp(-tau/mu0) at every level and F_up = 0.
    Grid: tau 0.01, 0.1, 1, 10; mu0 1, 0.5, 0.1; 4 and 16 streams.
    Tolerance 1e-12 relative: the beam is a closed form in DISORT, so only the round-off of exp()
    and of the layer sum of optical depths (four terms) enters.
(b) Energy closure. omega = 1 (pyharp clamps it to 1 - 1e-12 before DISORT; the direct pydisort
    run passes exactly 1), Henyey-Greenstein moments g^l, Lambertian surface albedo A. With no
    absorption in the medium the net flux F_dn - F_up is the same at every level and equals
    (1 - A) F_dn at the surface. Error: max over levels of |F_net - F_net(top)| / (mu0 F0) and
    |F_net(surface) - (1 - A) F_dn(surface)| / (mu0 F0).
    Grid: tau 0.1, 1, 10, 100; g 0, 0.5, 0.85; mu0 1, 0.5, 0.1; A 0, 0.3, 1; 4, 8, 16, 32 streams.
    Tolerance 1e-6 of mu0 F0: the energy the SSA margin can absorb is at most
    (1e-12) x tau / mu0 <= 1e-9 here; the rest is round-off of the band solve. 1e-6 leaves three
    orders of magnitude above the largest value measured.

Labels: [C1] beam through pyharp, [C2] beam through pydisort, [C3] closure through pyharp,
        [C4] closure through pydisort, [C5] R + T - 1 for A = 0 (part of [C3]/[C4], printed alone).

Needs: torch, numpy, pydisort and a pyharp built against that pydisort.
Run:   python ch03_beam_closure.py [--work DIR]   (default: a fresh temporary directory)
Pins:  PYHARP_WT and PYDISORT_SRC name the source trees; their commits are printed.
"""
import argparse
import itertools
import os
import subprocess
import sys
import tempfile

import numpy as np
import pydisort
import pyharp
import torch


def git_head(var):
    path = os.environ.get(var)
    if not path:
        return "unset"
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "not a git tree"


YAML = """species:
  - name: X
    composition: {{H: 2}}
geometry:
  cells:
    nx1: {nlyr}
opacities:
  slab:
    type: jit
    species: [X]
    nmom: {nmom}
    data: [{pt}]
bands:
  - name: sw
    range: [10000.0, 20000.0]
    opacities: [slab]
    solver: disort
    nwave: 1
    nstr: {nstr}
    flags: lamber,quiet,onlyfl
"""


class Slab(torch.nn.Module):
    """extinction k [1/m], single-scattering albedo, Henyey-Greenstein moments g^l"""

    def __init__(self, k: float, ssa: float, g: float, nmom: int):
        super().__init__()
        self.k = k
        self.ssa = ssa
        self.g = g
        self.nmom = nmom

    def forward(self, conc: torch.Tensor) -> torch.Tensor:
        out = torch.zeros((1, conc.shape[0], conc.shape[1], 2 + self.nmom), dtype=torch.float64)
        # fill_ keeps float64: under torch.jit.script, "out[..., 0] = self.k" rounds k to float32
        out[..., 0].fill_(self.k)
        out[..., 1].fill_(self.ssa)
        for m in range(1, self.nmom + 1):
            out[..., 1 + m].fill_(self.g ** m)
        return out


def pyharp_run(work, tau, ssa, g, mu0, alb, nstr, nlyr=4, ztot=1000.0):
    tag = f"{tau}_{ssa}_{g}_{nstr}"
    pt = os.path.join(work, f"slab_{tag}.pt")
    if not os.path.exists(pt):
        pyharp.compile(Slab(tau / ztot, ssa, g, nstr), pt)
    yp = os.path.join(work, f"sw_{tag}.yaml")
    with open(yp, "w") as f:
        f.write(YAML.format(nlyr=nlyr, nmom=nstr, pt=pt, nstr=nstr))
    bo = pyharp.RadiationOptions.from_yaml(yp).bands()[0]
    bo.weight([1.0])
    pyharp.disort_config(bo.disort(), nstr, nlyr, 1, 1)
    band = pyharp.RadiationBand(bo)
    conc = torch.ones((1, nlyr, 1), dtype=torch.float64)
    dz = torch.full((nlyr,), ztot / nlyr, dtype=torch.float64)
    bc = {"sw/umu0": torch.tensor([mu0], dtype=torch.float64),
          "sw/fbeam": torch.tensor([[1.0]], dtype=torch.float64),
          "sw/albedo": torch.tensor([[alb]], dtype=torch.float64)}
    # level temperatures are passed although 'planck' is off: see ch03_candidates.py [P3]
    atm = {"tempf": torch.full((1, nlyr + 1), 250.0, dtype=torch.float64)}
    flx = band.forward(conc, dz, bc, atm)  # (ncol, nlev, channel); level 0 is the surface
    up, dn = flx[0, :, 0].numpy()[::-1], flx[0, :, 1].numpy()[::-1]  # reorder: index 0 = top
    return np.linspace(0, tau, nlyr + 1), up, dn


def pydisort_run(tau, ssa, g, mu0, alb, nstr, nlyr=4):
    op = pydisort.DisortOptions().flags("lamber,quiet,onlyfl")
    op.ds().nlyr, op.ds().nstr, op.ds().nmom, op.ds().nphase = nlyr, nstr, nstr, nstr
    ds = pydisort.Disort(op)
    prop = torch.zeros((1, 1, nlyr, 2 + nstr), dtype=torch.float64)
    prop[..., 0] = tau / nlyr
    prop[..., 1] = ssa
    prop[..., 2:] = torch.tensor([g ** m for m in range(1, nstr + 1)], dtype=torch.float64)
    f = ds.forward(prop, "", None, umu0=torch.tensor([mu0], dtype=torch.float64),
                   fbeam=torch.tensor([[1.0]], dtype=torch.float64),
                   albedo=torch.tensor([[alb]], dtype=torch.float64))[0, 0].numpy()
    return np.linspace(0, tau, nlyr + 1), f[:, 0], f[:, 1]  # pydisort default order: index 0 = top


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="ch03_bc_")
    os.makedirs(work, exist_ok=True)
    torch.set_num_threads(1)
    print(f"python {sys.version.split()[0]}, torch {torch.__version__}, numpy {np.__version__}, "
          f"pydisort {pydisort.__version__}")
    print(f"pyharp source {git_head('PYHARP_WT')}, pydisort source {git_head('PYDISORT_SRC')}")
    runner = {"pyharp": lambda *x: pyharp_run(work, *x), "pydisort": pydisort_run}
    nfail = 0

    beam = {"pyharp": [0.0, 0.0], "pydisort": [0.0, 0.0]}
    for tau, mu0, nstr in itertools.product([0.01, 0.1, 1.0, 10.0], [1.0, 0.5, 0.1], [4, 16]):
        for path in beam:
            taus, up, dn = runner[path](tau, 0.0, 0.0, mu0, 0.0, nstr)
            ref = mu0 * np.exp(-taus / mu0)
            beam[path][0] = max(beam[path][0], float(np.max(np.abs(dn / ref - 1))))
            beam[path][1] = max(beam[path][1], float(np.max(np.abs(up)) / mu0))
    for lab, path in (("C1", "pyharp"), ("C2", "pydisort")):
        ok = max(beam[path]) <= 1e-12
        nfail += not ok
        print(f"[{lab}] {'PASS' if ok else 'FAIL'} Beer-Lambert via {path}: max rel dev F_dn "
              f"{beam[path][0]:.1e}, max F_up/(mu0 F0) {beam[path][1]:.1e} (tol 1e-12; 24 cases)")

    worst = {"pyharp": 0.0, "pydisort": 0.0}
    rt = {"pyharp": 0.0, "pydisort": 0.0}
    ncase = 0
    for tau, g, mu0, alb, nstr in itertools.product([0.1, 1.0, 10.0, 100.0], [0.0, 0.5, 0.85],
                                                    [1.0, 0.5, 0.1], [0.0, 0.3, 1.0], [4, 8, 16, 32]):
        ncase += 1
        for path in worst:
            taus, up, dn = runner[path](tau, 1.0, g, mu0, alb, nstr)
            net = dn - up
            if not np.isfinite(net).all():
                worst[path] = np.inf
                continue
            e = max(float(np.max(np.abs(net - net[0]))), abs(net[-1] - (1 - alb) * dn[-1])) / mu0
            worst[path] = max(worst[path], e)
            if alb == 0.0:
                rt[path] = max(rt[path], abs((up[0] + dn[-1]) / mu0 - 1))
    for lab, path in (("C3", "pyharp"), ("C4", "pydisort")):
        ok = worst[path] <= 1e-6
        nfail += not ok
        print(f"[{lab}] {'PASS' if ok else 'FAIL'} energy closure via {path}: max |dF_net|/(mu0 F0) "
              f"{worst[path]:.1e} (tol 1e-6; {ncase} cases)")
    ok = max(rt.values()) <= 1e-6
    nfail += not ok
    print(f"[C5] {'PASS' if ok else 'FAIL'} A = 0: max |R + T - 1| pyharp {rt['pyharp']:.1e}, "
          f"pydisort {rt['pydisort']:.1e} (tol 1e-6)")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
