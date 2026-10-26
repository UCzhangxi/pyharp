"""Check B: spectral-density vs band-integrated consistency through RadiationBand.

Physical set-up (identical in every variant): isothermal grey column, T = 250 K,
8 layers, total optical thickness 40 at every spectral point, surface at the same
temperature.  For such a column the band flux leaving the top is, exactly,

    F_up(TOA) = pi * int_band B_nu(T) dnu          [W m^-2]

independently of the two-stream closure or of the discrete-ordinate order, so the
reference is analytic (adaptive quadrature of the Planck function, CODATA 2018).

Three accumulation configurations of the SAME band are compared:

  W  weight mode, weights sum to 1 (correlated-k convention), the solver receives
     the band limits [wmin, wmax] -> solver output is a band-integrated flux.
  N  wavenumber mode as RadiationBandOptions::from_yaml builds it: every spectral
     point keeps wave_lower = wmin, wave_upper = wmax, and the band accumulator
     integrates over the wavenumber grid (flux_utils.cpp:17 -> trapezoid).
  D  wavenumber mode with wave_lower = wave_upper = nu_i, so the solver source is
     a spectral density and the trapezoid over nu is dimensionally consistent.

Reported quantity is R = F_band(measured) / F_band(reference).
"""

import json
import itertools
import numpy as np
import torch

from band_lab import (
    compile_grey,
    make_band,
    isothermal_column,
    run_band,
    toa_up,
)
from ch7_common import planck_flux_band

torch.set_default_dtype(torch.float64)
torch.set_num_threads(1)

T = 250.0
NLYR = 8
DZ = 1.0e3
KEXT = 5.0e-3  # total tau = 40

rows = []


def configure(bo, mode, wmin, wmax, nwave):
    nu = np.linspace(wmin, wmax, nwave)
    if mode == "weight":
        bo.weight([1.0 / nwave] * nwave)
    elif mode == "wavenumber":
        bo.wavenumber(list(nu))
    elif mode == "density":
        bo.wavenumber(list(nu))
        bo.set_wave_lower(list(nu))
        bo.set_wave_upper(list(nu))
    else:
        raise ValueError(mode)
    return nu


def one(solver, wmin, wmax, nwave, mode, albedo=0.0, nstr=4, kext=KEXT,
        btemp=None, temis=0.0, ttemp=0.0, tag=None):
    tag = tag or f"{solver}_{mode}_{nwave}_{int(wmax-wmin)}"
    f = compile_grey(f"op_{nwave}.pt", nwave, kext)
    flags = ("lamber,quiet,onlyfl,planck" if solver == "disort" else "planck")
    bo = make_band("bx", wmin, wmax, nwave, NLYR, solver, f,
                   nstr=nstr, flags=flags, tag=tag)
    configure(bo, mode, wmin, wmax, nwave)
    conc, dz, atm = isothermal_column(NLYR, T, DZ)
    flx = run_band(bo, conc, dz, atm, albedo=albedo, btemp=btemp,
                   temis=temis, ttemp=ttemp)
    meas = toa_up(flx)
    ref, _ = planck_flux_band(wmin, wmax, T)
    row = {
        "solver": solver, "mode": mode, "wmin": wmin, "wmax": wmax,
        "dnu": wmax - wmin, "nwave": nwave, "nstr": nstr, "albedo": albedo,
        "kext": kext, "measured": meas, "reference": ref, "ratio": meas / ref,
    }
    rows.append(row)
    return row


print("== B1: ratio vs band width and grid size, Toon LW ==")
print(f"{'solver':6s} {'mode':11s} {'dnu':>8s} {'nwave':>6s} "
      f"{'measured':>14s} {'reference':>14s} {'ratio':>14s}")
for solver in ("toon", "disort"):
    for dnu in (1.0, 10.0, 200.0, 1000.0):
        wmin, wmax = 700.0 - dnu / 2, 700.0 + dnu / 2
        for nwave in (2, 4, 8, 32, 128):
            for mode in ("weight", "wavenumber", "density"):
                r = one(solver, wmin, wmax, nwave, mode)
                print(f"{r['solver']:6s} {r['mode']:11s} {r['dnu']:8g} "
                      f"{r['nwave']:6d} {r['measured']:14.6e} "
                      f"{r['reference']:14.6e} {r['ratio']:14.6e}")

print("\n== B2: boundary / solver / opacity variations at dnu = 200, Toon+DISORT ==")
var = []
for solver in ("toon", "disort"):
    for albedo in (0.0, 0.3, 1.0):
        for kext in (5.0e-3, 1.0e-4, 1.0e-6):
            for mode in ("weight", "wavenumber"):
                r = one(solver, 600.0, 800.0, 16, mode, albedo=albedo,
                        kext=kext, tag=f"var_{solver}_{mode}")
                r["kind"] = "albedo/tau"
                var.append(r)
                print(f"{solver:6s} {mode:11s} albedo={albedo:4.1f} "
                      f"kext={kext:9.1e} ratio={r['ratio']:14.6e}")
for nstr in (4, 8, 16):
    for mode in ("weight", "wavenumber"):
        r = one("disort", 600.0, 800.0, 16, mode, nstr=nstr,
                tag=f"nstr_{nstr}_{mode}")
        r["kind"] = "nstr"
        var.append(r)
        print(f"disort {mode:11s} nstr={nstr:3d} ratio={r['ratio']:14.6e}")
for btemp, ttemp, temis in ((250.0, 0.0, 0.0), (300.0, 0.0, 0.0),
                            (250.0, 200.0, 1.0)):
    for mode in ("weight", "wavenumber"):
        r = one("disort", 600.0, 800.0, 16, mode, btemp=btemp, ttemp=ttemp,
                temis=temis, tag=f"bt_{int(btemp)}_{int(ttemp)}_{mode}")
        r["kind"] = "boundary temperature"
        var.append(r)
        print(f"disort {mode:11s} btemp={btemp:5.1f} ttemp={ttemp:5.1f} "
              f"temis={temis:3.1f} ratio={r['ratio']:14.6e}")

json.dump({"grid": rows}, open("results_b_band.json", "w"), indent=1)
print("\nwrote results_b_band.json")
