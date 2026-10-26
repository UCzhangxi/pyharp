"""Check A: isolate the Planck source from the spectral accumulator.

A1  pyharp.bbflux_wavenumber(wn, wn, T)      vs analytic B_nu(T)          [density]
A2  pyharp.bbflux_wavenumber(wn1, wn2, T)    vs quad(B_nu, wn1, wn2)      [band integral]
A3  pi * bbflux over the whole spectrum      vs sigma T^4
A4  bbflux_wavenumber(wave_tensor, T)        vs analytic B_nu(T)          [density overload]
A5  bbflux_wavelength                        vs analytic B_lambda
A6  the size of the "extra" factor: band integral / density = effective band width
"""

import json
import numpy as np
import torch
import pyharp

from ch7_common import (
    planck_wavenumber,
    planck_band_integral,
    SIGMA_SB,
    relerr,
)

torch.set_default_dtype(torch.float64)
torch.set_num_threads(1)

out = {"checks": []}


def rec(name, measured, reference, tol, note="", extra=None):
    e = relerr(measured, reference) if reference != 0 else abs(measured)
    r = {
        "id": name,
        "measured": measured,
        "reference": reference,
        "rel_err": e,
        "tol": tol,
        "pass": bool(e <= tol),
        "note": note,
    }
    if extra:
        r.update(extra)
    out["checks"].append(r)
    print(
        f"{name:28s} measured={measured:#.10g} ref={reference:#.10g} "
        f"relerr={e:.3e} tol={tol:.0e} {'PASS' if r['pass'] else 'FAIL'}  {note}"
    )
    return r


T = 250.0
temp = torch.tensor([T], dtype=torch.float64)

# ---------------------------------------------------------------- A1
# monochromatic branch: wn1 == wn2 (bbflux.cpp:46-50 / :117-121)
for nu in (100.0, 700.0, 2000.0):
    m = float(pyharp.bbflux_wavenumber(nu, nu, temp)[0])
    ref = float(planck_wavenumber(nu, T))
    rec(
        f"A1 mono wn={nu:g}",
        m,
        ref,
        1e-3,
        note="bbflux(wn,wn,T) vs B_nu [W m^-2 sr^-1 /cm^-1]",
        extra={"measured_over_reference": m / ref},
    )

# ---------------------------------------------------------------- A2
for (w1, w2) in ((600.0, 800.0), (690.0, 710.0), (699.5, 700.5),
                 (10.0, 3000.0), (1.0, 100.0)):
    m = float(pyharp.bbflux_wavenumber(w1, w2, temp)[0])
    ref, qerr = planck_band_integral(w1, w2, T)
    rec(
        f"A2 band [{w1:g},{w2:g}]",
        m,
        ref,
        2e-4,
        note="bbflux(wn1,wn2,T) vs quad(B_nu) [W m^-2 sr^-1]",
        extra={"quad_abs_err": qerr},
    )

# ---------------------------------------------------------------- A3
m = float(pyharp.bbflux_wavenumber(1e-6, 1e6, temp)[0]) * np.pi
rec("A3 full-spectrum sigma T^4", m, SIGMA_SB * T**4, 2e-4,
    note="pi*bbflux(0,inf,T) vs sigma T^4 [W m^-2]")

# ---------------------------------------------------------------- A4
wave = torch.tensor([100.0, 700.0, 2000.0], dtype=torch.float64)
dens = pyharp.bbflux_wavenumber(wave, T, 1).squeeze(-1)
for i, nu in enumerate([100.0, 700.0, 2000.0]):
    rec(f"A4 dens-overload wn={nu:g}", float(dens[i]),
        float(planck_wavenumber(nu, T)), 1e-3,
        note="bbflux_wavenumber(wave,T,ncol) vs B_nu")

# ---------------------------------------------------------------- A5
lam_um = torch.tensor([5.0, 14.2857142857, 100.0], dtype=torch.float64)
bl = pyharp.bbflux_wavelength(lam_um, T, 1).squeeze(-1)
for i, lam in enumerate([5.0, 14.2857142857, 100.0]):
    nu = 1.0e4 / lam
    # B_lambda = B_nu * nu^2 * 1e4 (per micron), from |dnu/dlambda|
    ref = float(planck_wavenumber(nu, T)) * nu**2 * 1e-4
    rec(f"A5 B_lambda lam={lam:g}um", float(bl[i]), ref, 2e-3,
        note="bbflux_wavelength vs B_nu*nu^2*1e-4 [W m^-2 sr^-1 /um]")

# ---------------------------------------------------------------- A6
# ratio of the band-integrated Planck to the density at band centre: this is the
# factor an extra integration over wavenumber would introduce.
print()
ratios = {}
for dnu in (1.0, 10.0, 200.0, 1000.0):
    w1, w2 = 700.0 - dnu / 2, 700.0 + dnu / 2
    band = float(pyharp.bbflux_wavenumber(w1, w2, temp)[0])
    dens_c = float(planck_wavenumber(0.5 * (w1 + w2), T))
    ratios[dnu] = band / dens_c
    print(f"A6 dnu={dnu:7g} cm^-1  band/density = {band/dens_c:12.6f} "
          f"(= effective width in cm^-1)")
out["A6_band_over_density"] = ratios

json.dump(out, open("results_a_planck.json", "w"), indent=1)
nfail = sum(1 for c in out["checks"] if not c["pass"])
print(f"\nA: {len(out['checks'])-nfail} pass, {nfail} fail")
