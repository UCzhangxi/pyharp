"""Check D: multi-bin bands, the two self-consistent conventions, and the
weight = bin-width pattern used by examples/jupiter_1d_rt.cpp.

A band [wmin, wmax] is split into nbin equal bins.  The solver receives each
bin's own [wave_lower, wave_upper], so the per-point flux is the flux
integrated over that bin [W m^-2].  Three accumulations are compared against
pi * int_band B_nu dnu for an isothermal, optically thick column:

  D-ck     weight_i = 1          (one g-point per bin)             -> expect 1
  D-width  weight_i = dnu_i      (examples/jupiter_1d_rt.cpp:90)   -> expect dnu_i
  D-ckg    weight_i = 1/ng per bin, ng g-points sharing a bin      -> expect 1
"""

import json
import numpy as np
import torch

from band_lab import compile_grey, make_band, isothermal_column, run_band, toa_up
from ch7_common import planck_flux_band

torch.set_default_dtype(torch.float64)
torch.set_num_threads(1)

T, NLYR, DZ, KEXT = 250.0, 8, 1.0e3, 5.0e-3
WMIN, WMAX = 600.0, 800.0
ref, _ = planck_flux_band(WMIN, WMAX, T)
rows = []
print(f"reference pi*int_600^800 B dnu = {ref:.8e} W/m^2\n")
print(f"{'convention':10s} {'nbin':>5s} {'ng':>3s} {'dnu_bin':>9s} "
      f"{'measured':>15s} {'ratio':>13s}")

for nbin in (2, 8, 200):
    dnu_bin = (WMAX - WMIN) / nbin
    edges = np.linspace(WMIN, WMAX, nbin + 1)
    lower, upper = edges[:-1], edges[1:]
    centre = 0.5 * (lower + upper)
    for conv, ng in (("ck", 1), ("width", 1), ("ckg", 4)):
        nwave = nbin * ng
        f = compile_grey(f"d_{nwave}.pt", nwave, KEXT)
        bo = make_band("bx", WMIN, WMAX, nwave, NLYR, "disort", f,
                       flags="lamber,quiet,onlyfl,planck",
                       tag=f"d_{conv}_{nbin}")
        lo = np.repeat(lower, ng)
        up = np.repeat(upper, ng)
        bo.set_wave_lower(list(lo))
        bo.set_wave_upper(list(up))
        if conv == "ck":
            w = np.ones(nwave)
        elif conv == "width":
            w = np.repeat(upper - lower, ng)
        else:
            w = np.ones(nwave) / ng
        bo.weight(list(w))
        conc, dz, atm = isothermal_column(NLYR, T, DZ)
        flx = run_band(bo, conc, dz, atm)
        m = toa_up(flx)
        rows.append({"convention": conv, "nbin": nbin, "ng": ng,
                     "dnu_bin": dnu_bin, "measured": m, "reference": ref,
                     "ratio": m / ref})
        print(f"{conv:10s} {nbin:5d} {ng:3d} {dnu_bin:9.3f} {m:15.6e} "
              f"{m/ref:13.6f}")

json.dump({"rows": rows}, open("results_d_bins.json", "w"), indent=1)
print("\nwrote results_d_bins.json")
