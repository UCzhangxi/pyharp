"""ch08 check: the spherical flux scaling of Radiation.forward (atm keys `area`, `vol`, `dz`).

The documented intent (flux_utils.hpp, spherical_flux_scaling): with H_i = (F_{i+1} - F_i) V_i / dz_i the heating of
layer i in the plane-parallel solution, find factors x_q on the levels with x_L = 1 at the top and
x_{i+1} F_{i+1} A_{i+1} - x_i F_i A_i = H_i, i.e. x_i = (x_{i+1} F_{i+1} A_{i+1} - H_i) / (F_i A_i), so that the scaled
fluxes x F heat every layer of the curved column as the plane-parallel fluxes heat the flat one. The code at the pin
computes x_i = (x_{i+1} F_{i+1} A_{i+1} - H_i) / A_i instead.

Case: the two-band column of ch08_common (4 layers of 250 m), net flux F from Radiation.forward without `area`, then
with `area` (ncol, nlev), `vol` (ncol, nlyr) and `dz` (ncol, nlyr) in atm. Geometries: plane-parallel (A = 10 m^2 on
every level, V = A dz) and a spherical shell (A_q = r_q^2 per steradian, V_i = (r_{i+1}^3 - r_i^3)/3, r_0 = 6.4e6 m).

  [C1] sympy: in the plane-parallel geometry the documented recursion gives x_i = 1 on every level, for any fluxes
       (one step, exact).
  [C2] a numpy port of the code's recursion (line for line against spherical_flux_scaling) applied to the plain
       net flux reproduces pyharp's scaled/plain ratio of the net flux, in both geometries (tol 1e-13 relative: four
       products and a quotient per level, compounded over 4 levels).
  [C3] the shapes the code needs: `area` with nlev entries per column (nlyr entries are refused), and `dz` in atm
       (not only the dz argument).
  [P1] CANDIDATE, the code's factor in the plane-parallel geometry: x_q differs from 1 (it equals F_q on the level
       below the top), and the scaled net flux no longer heats the layers as the plain one does; the documented
       recursion, ported, gives x = 1 there to 1e-15.

The per-level factors are printed for the figure of the chapter (lines starting `level`).
Needs: torch, numpy, sympy, pydisort and a pyharp built against that pydisort.
Run:   python ch08_spherical.py [--work DIR]   (default: a fresh temporary directory)
"""
import argparse
import os
import sys
import tempfile

import numpy as np
import pyharp
import sympy as sp
import torch

from ch08_common import F64, header, set_unit_weights, two_band_inputs, two_band_yaml

R0 = 6.4e6


def code_port(flx, dz, area, vol):
    """spherical_flux_scaling at the pin, line for line (numpy, last axis = level or layer)"""
    nx1 = dz.shape[-1]
    kappa = np.ones_like(flx)
    volh = (flx[..., 1:nx1 + 1] - flx[..., 0:nx1]) / dz * vol
    for i in range(nx1 - 1, -1, -1):
        kappa[..., i] = (kappa[..., i + 1] * flx[..., i + 1] * area[..., i + 1] - volh[..., i]) / area[..., i]
    return kappa


def documented(flx, dz, area, vol):
    """the recursion of the docstring (Formula 3): divide by F_i A_i"""
    nx1 = dz.shape[-1]
    x = np.ones_like(flx)
    h = (flx[..., 1:nx1 + 1] - flx[..., 0:nx1]) / dz * vol
    for i in range(nx1 - 1, -1, -1):
        x[..., i] = (x[..., i + 1] * flx[..., i + 1] * area[..., i + 1] - h[..., i]) / (flx[..., i] * area[..., i])
    return x


def geometry(kind, dz):
    nl = dz.shape[-1]
    if kind == "plane-parallel":
        area = np.full((1, nl + 1), 10.0)
        vol = 10.0 * dz[None, :]
    else:
        r = R0 + np.concatenate([[0.0], np.cumsum(dz)])
        area = (r ** 2)[None, :]
        vol = ((r[1:] ** 3 - r[:-1] ** 3) / 3.0)[None, :]
    return area, vol


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    work = ap.parse_args().work or tempfile.mkdtemp(prefix="ch08_sph_")
    os.makedirs(work, exist_ok=True)
    torch.set_num_threads(1)
    header(f", pyharp {pyharp.__version__}, sympy {sp.__version__}")
    rad = pyharp.Radiation(set_unit_weights(pyharp.RadiationOptions.from_yaml(two_band_yaml(work))))
    conc, dz, bc, atm = two_band_inputs()
    nfail = 0

    def forward(extra):
        a = {k: v.clone() for k, v in atm.items()}
        a.update(extra)
        return rad.forward(conc, dz, {k: v.clone() for k, v in bc.items()}, a)

    net0 = forward({})[0].numpy()

    fi, fi1, a, h = sp.symbols("F_i F_ip1 A dz", positive=True)
    xi = (1 * fi1 * a - (fi1 - fi) * (a * h) / h) / (fi * a)
    ok1 = sp.simplify(xi - 1) == 0
    nfail += not ok1
    print(f"[C1] {'PASS' if ok1 else 'FAIL'} sympy: documented recursion with A constant and V = A dz gives "
          f"x_i = {sp.simplify(xi)} from x_(i+1) = 1")

    dzn = dz.numpy()
    res, dev2 = {}, 0.0
    for kind in ("plane-parallel", "shell"):
        area, vol = geometry(kind, dzn)
        extra = {"area": torch.tensor(area, dtype=F64), "vol": torch.tensor(vol, dtype=F64),
                 "dz": torch.tensor(dzn[None, :], dtype=F64)}
        net1, sfc1, toa1 = forward(extra)
        ratio = net1.numpy() / net0
        port = code_port(net0, dzn[None, :], area, vol)
        dev2 = max(dev2, float(np.max(np.abs(ratio / port - 1))))
        res[kind] = (ratio, documented(net0, dzn[None, :], area, vol), net1.numpy(), area, vol)
    ok2 = dev2 <= 1e-13
    nfail += not ok2
    print(f"[C2] {'PASS' if ok2 else 'FAIL'} numpy port of the code's recursion = pyharp scaled/plain net flux, "
          f"plane-parallel and shell: max rel dev {dev2:.1e} (tol 1e-13)")

    area, vol = geometry("shell", dzn)
    short = {"area": torch.tensor(area[:, :-1], dtype=F64), "vol": torch.tensor(vol, dtype=F64),
             "dz": torch.tensor(dzn[None, :], dtype=F64)}
    nodz = {"area": torch.tensor(area, dtype=F64), "vol": torch.tensor(vol, dtype=F64)}
    refused = []
    for extra in (short, nodz):
        try:
            forward(extra)
            refused.append(False)
        except Exception:  # noqa: BLE001
            refused.append(True)
    ok3 = all(refused)
    nfail += not ok3
    print(f"[C3] {'PASS' if ok3 else 'FAIL'} area with nlyr entries refused: {refused[0]}; area without 'dz' in atm "
          f"refused: {refused[1]}")

    ratio, doc, net1, area, vol = res["plane-parallel"]
    dev_doc = float(np.max(np.abs(doc - 1)))
    dev_code = float(np.max(np.abs(ratio - 1)))
    heat0 = np.diff(net0 * area, axis=-1) / vol
    heat1 = np.diff(net1 * area, axis=-1) / vol
    hdev = float(np.max(np.abs(heat1 / heat0 - 1)))
    rep = dev_code > 1e-6 and dev_doc <= 1e-15
    print(f"[P1] CANDIDATE {'reproduced' if rep else 'not reproduced'} plane-parallel geometry: code factor max "
          f"|x - 1| {dev_code:.2e} (x below the top = {ratio[0, -2]:.4f}, F there = {net0[0, -2]:.4f} W m-2), "
          f"documented recursion max |x - 1| {dev_doc:.1e}; layer heating changed by up to {hdev:.2e} relative")
    for kind in ("plane-parallel", "shell"):
        r, d = res[kind][0], res[kind][1]
        for q in range(r.shape[-1]):
            print(f"level {kind:14s} {q} code {r[0, q]:.6e} documented {d[0, q]:.6e}")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
