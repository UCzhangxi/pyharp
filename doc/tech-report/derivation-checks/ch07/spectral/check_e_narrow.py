"""Check E: conditioning of the band-integrated Planck for narrow intervals.

harp::bbflux_wavenumber(wn1, wn2, temp) is a port of cdisort's c_planck_func2
(same VCUT, conc, sigdpi, A1..A6 and vcp tables), but it drops the Simpson-rule
branch that c_planck_func2 takes when (wnumhi - wnumlo)/wnumhi < 1e-2, and it
keeps the difference of two to-infinity series instead.  This check measures the
resulting error as the interval narrows, against adaptive quadrature of the
Planck function built from CODATA-2018 constants.
"""

import json
import numpy as np
import torch
import pyharp

from ch7_common import planck_band_integral, planck_wavenumber

torch.set_default_dtype(torch.float64)
torch.set_num_threads(1)

rows = []
print(f"{'T':>6s} {'nu0':>7s} {'dnu':>10s} {'rel_width':>10s} "
      f"{'bbflux':>15s} {'quad':>15s} {'rel_err':>11s}")
for T in (100.0, 250.0, 600.0):
    temp = torch.tensor([T], dtype=torch.float64)
    for nu0 in (100.0, 700.0, 2500.0):
        for dnu in (100.0, 10.0, 1.0, 1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6):
            w1, w2 = nu0 - dnu / 2, nu0 + dnu / 2
            m = float(pyharp.bbflux_wavenumber(w1, w2, temp)[0])
            ref, _ = planck_band_integral(w1, w2, T)
            e = abs(m - ref) / abs(ref)
            rows.append({"T": T, "nu0": nu0, "dnu": dnu,
                         "rel_width": dnu / nu0, "bbflux": m, "quad": ref,
                         "rel_err": e})
            print(f"{T:6.0f} {nu0:7.0f} {dnu:10.1e} {dnu/nu0:10.1e} "
                  f"{m:15.6e} {ref:15.6e} {e:11.3e}")

worst = max(rows, key=lambda r: r["rel_err"])
print(f"\nworst relative error {worst['rel_err']:.3e} at T={worst['T']:g} K, "
      f"nu0={worst['nu0']:g}, dnu={worst['dnu']:g} cm^-1")
narrow = [r for r in rows if r["rel_width"] < 1e-2]
wide = [r for r in rows if r["rel_width"] >= 1e-2]
print(f"max rel err, (dnu/nu) <  1e-2 (cdisort would use Simpson): "
      f"{max(r['rel_err'] for r in narrow):.3e}")
print(f"max rel err, (dnu/nu) >= 1e-2:                              "
      f"{max(r['rel_err'] for r in wide):.3e}")

json.dump({"rows": rows}, open("results_e_narrow.json", "w"), indent=1)
print("\nwrote results_e_narrow.json")
