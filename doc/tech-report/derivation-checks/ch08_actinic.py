"""ch08 check: where a mean intensity (and so an actinic flux) can be read at the pin.

pyharp computes no actinic flux: RadiationBand returns four flux channels per level. A DISORT band keeps its pydisort
module as the child `solver`; after the band's forward, `solver.gather_flx()` returns cdisort's eight flux outputs per
spectral point, column and level (bottom first when `upward` is set), among them the mean intensity `uavg` (column
pydisort.kIUAVG) and its direct-beam part `uavgso` (column pydisort.kIUAVGSO).

Case: one purely absorbing layer stack (4 layers, total optical depth 0.4, omega = 0, no Planck source, black surface),
beam fbeam = F0 = 100 at mu0 = 0.6. There is no diffuse light, so the mean intensity is the direct beam's,
ubar(tau) = F0 exp(-tau / mu0) / (4 pi), and the actinic flux 4 pi ubar = F0 exp(-tau / mu0).

  [C1] the band's flux output has 4 channels per level, and the DISORT band's `solver` is a pydisort Disort module.
  [C2] gather_flx() column kIUAVG equals F0 exp(-tau/mu0) / (4 pi) at every level, column kIUAVGSO equals it too, and
       the downward flux the band returns equals mu0 F0 exp(-tau/mu0) (tol 1e-12 relative: one exp, as the Beer-Lambert
       check of chapter 3).
  [C3] a Toon band's `solver` has no gather_flx: no mean intensity is available from a Toon band.

Needs: torch, numpy, pydisort and a pyharp built against that pydisort.
Run:   python ch08_actinic.py [--work DIR]   (default: a fresh temporary directory)
"""
import argparse
import math
import os
import sys
import tempfile

import pydisort
import pyharp
import torch

from ch08_common import F64, compile_slab, header, set_unit_weights, write

NL, ZTOT, TAU, MU0, F0 = 4, 1000.0, 0.4, 0.6, 100.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    work = ap.parse_args().work or tempfile.mkdtemp(prefix="ch08_act_")
    os.makedirs(work, exist_ok=True)
    torch.set_num_threads(1)
    header(f", pyharp {pyharp.__version__}")
    pt = compile_slab(work, "absorber", TAU / ZTOT)
    path = write(work, "absorber.yaml", f"""species:
  - name: X
    composition: {{H: 2}}
geometry:
  cells:
    nx1: {NL}
opacities:
  oa: {{type: jit, species: [X], data: [{pt}]}}
bands:
  - name: sw
    range: [10000.0, 20000.0]
    opacities: [oa]
    solver: disort
    nwave: 1
    nstr: 4
    flags: lamber,quiet,onlyfl
  - name: tw
    range: [10000.0, 20000.0]
    opacities: [oa]
    solver: toon
    nwave: 1
""")
    op = set_unit_weights(pyharp.RadiationOptions.from_yaml(path))
    conc = torch.ones((1, NL, 1), dtype=F64)
    dz = torch.full((NL,), ZTOT / NL, dtype=F64)
    bc = {"sw/umu0": torch.tensor([MU0], dtype=F64), "sw/fbeam": torch.tensor([[F0]], dtype=F64),
          "sw/albedo": torch.zeros((1, 1), dtype=F64)}
    atm = {"tempf": torch.full((1, NL + 1), 250.0, dtype=F64)}
    nfail = 0

    band = pyharp.RadiationBand(op.bands()[0])
    flx = band.forward(conc, dz, dict(bc), dict(atm))
    solver = dict(band.named_children())["solver"]
    ok1 = flx.shape[-1] == 4 and type(solver).__name__ == "Disort" and hasattr(solver, "gather_flx")
    nfail += not ok1
    print(f"[C1] {'PASS' if ok1 else 'FAIL'} band output shape {tuple(flx.shape)} (4 channels); DISORT band solver is "
          f"pydisort {type(solver).__name__} with gather_flx: {hasattr(solver, 'gather_flx')}")

    g = solver.gather_flx()[0, 0]                 # (nlev, 8), level 0 = surface
    tau = torch.linspace(TAU, 0.0, NL + 1, dtype=F64)   # optical depth from the top, at levels surface..top
    ubar = F0 * torch.exp(-tau / MU0) / (4 * math.pi)
    d_avg = (g[:, pydisort.kIUAVG] / ubar - 1).abs().max().item()
    d_so = (g[:, pydisort.kIUAVGSO] / ubar - 1).abs().max().item()
    d_dn = (flx[0, :, 1] / (MU0 * F0 * torch.exp(-tau / MU0)) - 1).abs().max().item()
    ok2 = max(d_avg, d_so, d_dn) <= 1e-12
    nfail += not ok2
    print(f"[C2] {'PASS' if ok2 else 'FAIL'} gather_flx uavg = F0 exp(-tau/mu0)/(4 pi): max rel dev {d_avg:.1e}; "
          f"uavgso {d_so:.1e}; band F_dn = mu0 F0 exp(-tau/mu0) {d_dn:.1e} (tol 1e-12); actinic flux 4 pi uavg at "
          f"the surface {4 * math.pi * g[0, pydisort.kIUAVG].item():.6f} (F0 exp(-tau/mu0) = "
          f"{F0 * math.exp(-TAU / MU0):.6f})")

    tband = pyharp.RadiationBand(op.bands()[1])
    tsolver = dict(tband.named_children()).get("solver")
    ok3 = tsolver is not None and not hasattr(tsolver, "gather_flx")
    nfail += not ok3
    print(f"[C3] {'PASS' if ok3 else 'FAIL'} Toon band solver {type(tsolver).__name__}: gather_flx "
          f"{'absent' if ok3 else 'present'}")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
