#!/usr/bin/env python3
"""Chapter 10 check: zero in, zero out for the opacity modules a band can call without a data file, and the
outputs every clamp or floor of those modules acts on.

usage: python -I opacity_probe.py [--tree <pyharp tree>] [--dump <file.npz>]

[Z4] a layer with zero condensate concentration has zero extinction and finite properties in every module (`water-ice-fu96-98`, `water-liquid-mie`, `water-cloud-temperature-switch`), and the band built on it
     gives that layer zero optical depth and zero single-scattering albedo (the band weights each module's albedo
     by its extinction, so a module's albedo where its extinction is 0 does not reach the solver).
[Z5] the log-space table interpolation (`interpn`, the call the table opacities make after taking the log of their
     cross sections) between a zero entry, stored as the module's floor, and a positive entry: the floor must not
     move the answer (against no floor, log 0 = -inf).
[Z6] the table interpolation outside the table: constant extrapolation, the end value (the weight clamp).
`--tree` reads the floor constants of [Z5] from that pyharp tree (default: the values at the pin).
`--dump` writes the module outputs over the probe grid, so two builds can be compared (`break_tests.sh`). Exits
with the number of failed claims. CPU, double.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile

import numpy as np
import torch
import pyharp
from pyharp.opacity import FuWaterIce, MieWaterLiquid, TemperatureSwitchWaterCloud

torch.set_default_dtype(torch.float64)

YAML = """species:
  - name: {sp}
    composition: {{H: 2, O: 1}}
geometry:
  cells:
    nx1: {nlyr}
opacities:
  cloud:
    type: {kind}
    species: [{sp}]
    nmom: {nmom}
bands:
  - name: shortwave
    range: [100., 50000.]
    opacities: [cloud]
    solver: toon
    nwave: {nwave}
    nstr: 2
"""
# wavelengths 0.2-120 um: below, inside and above the 0.25-100 um support of the Fu parameterization
WAVELENGTH_UM = np.array([0.2, 0.25, 0.55, 1.0, 3.0, 3.99, 4.0, 10.0, 50.0, 70.0, 100.0, 120.0])
WAVENUMBER = (1.0e4 / WAVELENGTH_UM).tolist()


def band_options(kind: str, sp: str, nlyr: int, nmom: int, work: str):
    fn = os.path.join(work, f"{kind}.yaml")
    with open(fn, "w") as f:
        f.write(YAML.format(kind=kind, sp=sp, nlyr=nlyr, nmom=nmom, nwave=len(WAVENUMBER)))
    op = pyharp.RadiationOptions.from_yaml(fn)
    b = op.bands()[0]
    b.wavenumber(WAVENUMBER).weight([1.0 / len(WAVENUMBER)] * len(WAVENUMBER))
    return b


# the table floors of [Z5]: (file, regex of the constant, label); the defaults are their values at the pin
FLOOR_SITES = [
    ("src/opacity/picaso_ck.cpp", r"clamp_min\(([0-9.eE+-]+)\)", "picaso-ck", 1e-300),
    ("src/opacity/respq_table.cpp", r"clamp_min\(([0-9.eE+-]+)\)", "respq-table", 1e-300),
    ("src/utils/netcdf_opacity_utils.hpp", r"fill_value = ([0-9.eE+-]+);", "NetCDF fill", 1e-300),
    ("src/opacity/helios.cpp", r"clamp_\(([0-9.eE+-]+)\)\.log_", "helios", 1e-99),
]


def floors(tree):
    import re
    out = []
    for path, rx, label, default in FLOOR_SITES:
        v = default
        if tree:
            m = re.search(rx, open(os.path.join(tree, path)).read())
            v = float(m.group(1))
        out.append((label, v))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree")
    ap.add_argument("--dump")
    args = ap.parse_args()
    work = tempfile.mkdtemp(prefix="ch10opa-")
    fails = 0
    dump = {}
    wn = torch.tensor(WAVENUMBER)
    print(f"[O0] pyharp {pyharp.__version__}, torch {torch.__version__}, numpy {np.__version__}, "
          f"Python {sys.version.split()[0]}; CPU, double; {len(WAVENUMBER)} wavelengths 0.2-120 um")

    # layer concentrations [mol/m^3]: zero, tiny, normal; temperatures across the ice/liquid switch
    conc = torch.tensor([[0.0, 1e-30, 1e-6, 1e-3, 1e-2, 0.0]]).unsqueeze(-1)
    temp = torch.tensor([[200.0, 240.0, 253.15, 263.0, 273.15, 290.0]])
    nlyr = conc.shape[1]
    zero_layers = [0, nlyr - 1]
    cases = []
    ice = FuWaterIce(band_options("water-ice-fu96-98", "H2O(s)", nlyr, 3, work).opacities()["cloud"])
    cases.append(("fu96-98 (temp)", "water-ice-fu96-98", "H2O(s)", 3, ice, {"wavenumber": wn, "temp": temp}))
    cases.append(("fu96-98 (re)", "water-ice-fu96-98", "H2O(s)", 3, ice,
                  {"wavenumber": wn, "re": torch.tensor([[13.0, 20.0, 30.0, 50.0, 70.0, 84.0]])}))
    mie = MieWaterLiquid(band_options("water-liquid-mie", "H2O(l)", nlyr, 3, work).opacities()["cloud"])
    cases.append(("liquid mie", "water-liquid-mie", "H2O(l)", 3, mie,
                  {"wavenumber": wn, "re": torch.tensor([[2.0, 5.0, 10.0, 15.0, 25.0, 40.0]])}))
    sw = TemperatureSwitchWaterCloud(
        band_options("water-cloud-temperature-switch", "H2O(s)", nlyr, 2, work).opacities()["cloud"])
    cases.append(("temperature switch", "water-cloud-temperature-switch", "H2O(s)", 2, sw,
                  {"wavenumber": wn, "temp": temp}))

    worst_zero, worst_case, nonfinite = 0.0, "", []
    for name, kind, sp, nmom, mod, atm in cases:
        out = mod.forward(conc, atm).numpy()
        dump[name] = out
        if not np.all(np.isfinite(out)):
            nonfinite.append(name)
        z = float(np.max(np.abs(out[:, :, zero_layers, 0])))  # a module's albedo is unweighted where ext = 0
        if z >= worst_zero:
            worst_zero, worst_case = z, name
        print(f"[Z4] {name:19s} max |extinction| in zero-concentration layers {z:.1e}; "
              f"min albedo {out[..., 1].min():.3g}, max albedo {out[..., 1].max():.6g}; "
              f"|g| max {np.abs(out[..., 2]).max():.6g}; finite {bool(np.all(np.isfinite(out)))}")
        # the band on top of it: a zero-concentration layer must leave the beam unchanged
        bop = band_options(kind, sp, nlyr, nmom, work)
        band = pyharp.RadiationBand(bop)
        nw = len(WAVENUMBER)
        bc = {"shortwave/fbeam": torch.ones(nw, 1), "shortwave/umu0": torch.tensor([0.5]),
              "shortwave/albedo": torch.zeros(nw, 1)}
        band.forward(conc, torch.full((nlyr,), 100.0), bc, dict(atm))
        prop = band.buffer("prop").numpy()
        zp = float(np.max(np.abs(prop[:, :, zero_layers, :2])))
        if not np.all(np.isfinite(prop)):
            nonfinite.append(name + " band")
        if zp >= worst_zero:
            worst_zero, worst_case = zp, name + " band"
        dump[name + " band"] = prop
    ok = worst_zero == 0.0 and not nonfinite
    fails += not ok
    print(f"[Z4] {'PASS' if ok else 'FAIL'} zero condensate in, zero extinction out (module) and zero optical "
          f"depth and albedo (band): max {worst_zero:.1e} at {worst_case}, tolerance 0 (exact); non-finite: {nonfinite}")

    # Z5: log-space interpolation between a zero table entry (stored as a floor) and a positive one
    k = 1.0e-24
    q = torch.tensor([0.0, 0.25, 0.5, 1.0])  # query between node 0 (zero entry) and node 1 (k)
    coord = torch.tensor([0.0, 1.0])

    def interp(floor):
        table = torch.tensor([floor, k]).log().view(2, 1)
        return pyharp.interpn([q], [coord], table).squeeze(-1).exp().numpy()

    none = interp(0.0)
    print(f"[Z5] no floor (log 0 = -inf): exp(interp ln sigma) at x = 0, 0.25, 0.5, 1 of [0, {k:g}]: "
          + ", ".join(f"{v:.3g}" for v in none) + "; linear interpolation would give "
          + ", ".join(f"{k * x:.3g}" for x in q.numpy()))
    worst, where = 0.0, ""
    for label, floor in floors(args.tree):
        val = interp(floor)
        dump[f"interpn floor {label}"] = val
        shift = float(np.max(np.abs(val - none))) / k if np.all(np.isfinite(val)) else math.inf
        print(f"[Z5] floor {floor:.0e} ({label}): " + ", ".join(f"{v:.3g}" for v in val)
              + f"; max |sigma(floor) - sigma(no floor)| / sigma(1) = {shift:.1e}")
        if shift >= worst:
            worst, where = shift, f"{label} ({floor:.0e})"
    ok = worst <= 1e-12
    fails += not ok
    print(f"[Z5] {'PASS' if ok else 'FAIL'} a table floor does not move the interpolated cross section: max "
          f"|sigma(floor) - sigma(no floor)| / sigma(1) = {worst:.1e} at {where}, tolerance 1e-12; between a zero and a "
          f"positive entry the log-space interpolation, not the floor, sets the value (1e-162 against 5e-25 linear at "
          f"x = 0.5 for the 1e-300 floor)")

    # Z6: outside the table the interpolation returns the end value
    table = torch.tensor([[1.0], [2.0], [4.0]])
    coord3 = torch.tensor([0.0, 1.0, 2.0])
    qo = torch.tensor([-5.0, -0.5, 0.0, 1.5, 2.0, 2.5, 10.0])
    val = pyharp.interpn([qo], [coord3], table).squeeze(-1).numpy()
    expect = np.array([1.0, 1.0, 1.0, 3.0, 4.0, 4.0, 4.0])
    dump["interpn outside"] = val
    dev = float(np.max(np.abs(val - expect)))
    fails += dev > 0.0
    print(f"[Z6] {'PASS' if dev == 0.0 else 'FAIL'} interpolation outside the table is constant at the end value: "
          f"values at x = {qo.tolist()} are {val.tolist()}, max deviation {dev:.1e}, tolerance 0")

    if args.dump:
        np.savez(args.dump, **{k_.replace(' ', '_'): v for k_, v in dump.items()})
    print(f"[O9] {fails} failed")
    return fails


if __name__ == "__main__":
    sys.exit(main())
