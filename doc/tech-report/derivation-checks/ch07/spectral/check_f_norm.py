"""Check F: band normalization.

Hogan & Matricardi (2020), GMD 13, 6501-6521, Sect. 4.2 (p. 6512) states the
longwave convention a CKD model must satisfy: the Planck function supplied for
each k term is "integrated over the parts of the spectrum contributing to each
k term" and, at a given layer interface, "these values should sum to sigma T^4".

So, for a tiling of the spectrum into bins:
  F1  pi * sum_i bbflux(bin_i)                 == sigma T^4   (plain sum)
  F2  trapezoid over nu of the same values     != sigma T^4   (the extra integral)
"""

import json
import numpy as np
import torch
import pyharp

from ch7_common import SIGMA_SB

torch.set_default_dtype(torch.float64)
T = 250.0
temp = torch.tensor([T], dtype=torch.float64)
target = SIGMA_SB * T ** 4

rows = []
print(f"sigma T^4 = {target:.8f} W/m^2 at T = {T:g} K\n")
print(f"{'nbin':>6s} {'dnu_bin':>9s} {'pi*sum':>16s} {'sum/sigT4':>12s} "
      f"{'pi*trapz':>16s} {'trapz/sigT4':>14s}")
for nbin in (1, 10, 100, 1000):
    edges = np.linspace(1.0e-6, 6000.0, nbin + 1)
    vals = np.array([
        float(pyharp.bbflux_wavenumber(float(a), float(b), temp)[0])
        for a, b in zip(edges[:-1], edges[1:])
    ])
    centre = 0.5 * (edges[:-1] + edges[1:])
    s = np.pi * vals.sum()
    tz = np.pi * (np.trapezoid(vals, centre) if nbin > 1 else 0.0)
    rows.append({"nbin": nbin, "dnu_bin": float(edges[1] - edges[0]),
                 "pi_sum": float(s), "sum_over_sigmaT4": float(s / target),
                 "pi_trapz": float(tz),
                 "trapz_over_sigmaT4": float(tz / target)})
    print(f"{nbin:6d} {edges[1]-edges[0]:9.2f} {s:16.6f} {s/target:12.6f} "
          f"{tz:16.6f} {tz/target:14.4f}")

json.dump({"rows": rows, "sigma_T4": target}, open("results_f_norm.json", "w"),
          indent=1)
print("\nwrote results_f_norm.json")
