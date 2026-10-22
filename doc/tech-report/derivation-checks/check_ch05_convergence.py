"""ch05: convergence of DISORT in the number of streams, and the choice of the reference stream count N_ref.

DISORT (pyharp.disort_config + pydisort.Disort, the path pyharp's RadiationBand uses) runs the ch05 grid of
homogeneous slabs (ch05_common: 864 shortwave columns, 240 thermal columns) at NSTR = 4 ... 128 streams, with
NSTR Henyey-Greenstein moments chi_l = g^l, so the delta-M truncation fraction is f = g^NSTR.

    d(N) = max over grid, levels and both channels of |F(N) - F(2N)| / F_inc,

F_inc = mu0 F0 (shortwave) or pi B_band(T_surface) (thermal). N_ref is the smallest N with d(N) <= TOL_REF.

Run: python3 check_ch05_convergence.py [--data DIR]  (from any directory; pyharp built at the code pin).
Exit status: the number of FAIL lines.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch05_common as C  # noqa: E402

NSTR = [4, 8, 16, 32, 64, 128]
# 1e-5 of the incident flux: at least 65 times below the median Toon-vs-DISORT error on the grid (1.06e-3 beam,
# 6.52e-4 thermal; check_ch05_toon_vs_disort.out [C3], [C37]).
TOL_REF = 1.0e-5


def run_sw(nstr, g):
    pm = np.repeat(C.hg_moments(g["g"], nstr)[:, None, :], C.NLYR_SW, 1)
    f = C.run_disort_sw(nstr, C.layers(g["tau"], C.NLYR_SW), C.same(g["ssa"], C.NLYR_SW), pm, g["mu0"],
                        g["albedo"])
    return f / g["mu0"][:, None, None]


def run_lw(nstr, g):
    pm = np.repeat(C.hg_moments(g["g"], nstr)[:, None, :], C.NLYR_LW, 1)
    f = C.run_disort_lw(nstr, C.layers(g["tau"], C.NLYR_LW), C.same(g["ssa"], C.NLYR_LW), pm,
                        C.lw_temf(len(g["tau"])), g["albedo"], C.WAVE_LO, C.WAVE_HI)
    return f / C.band_planck_flux(C.T_BOT, C.WAVE_LO, C.WAVE_HI)


def converge(name, runner, grid, ck):
    res = {n: runner(n, grid) for n in NSTR}
    d = {}
    for a, b in zip(NSTR[:-1], NSTR[1:]):
        diff = np.abs(res[a] - res[b])
        d[a] = float(diff.max())
        i = int(np.unravel_index(np.argmax(diff), diff.shape)[0])
        where = ", ".join(f"{k}={grid[k][i]:g}" for k in grid)
        ck.info(f"{name} d({a}) = max|F({a}) - F({b})|/F_inc", f"{d[a]:.3e} at {where}")
    nref = next((a for a in NSTR[:-1] if d[a] <= TOL_REF), None)
    if nref is None:
        ck.check(f"{name} N_ref exists with d(N_ref) <= {TOL_REF:g}", float("inf"), TOL_REF)
        return None, d
    ck.check(f"{name} N_ref = {nref}: d(N_ref)", d[nref], TOL_REF)
    ck.check(f"{name} |F(N_ref) - F({NSTR[-1]})|/F_inc", float(np.abs(res[nref] - res[NSTR[-1]]).max()), TOL_REF)
    return nref, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="write the figure data (json) into this directory")
    a = ap.parse_args()
    print(C.version_line())
    print(C.env_line())
    ck = C.Checker()
    nsw, dsw = converge("SW", run_sw, C.sw_grid(), ck)
    nlw, dlw = converge("LW", run_lw, C.lw_grid(), ck)
    if a.data:
        os.makedirs(a.data, exist_ok=True)
        with open(os.path.join(a.data, "convergence.json"), "w") as f:
            json.dump({"nstr": NSTR[:-1], "tol_ref": TOL_REF, "sw": [dsw[n] for n in NSTR[:-1]],
                       "lw": [dlw[n] for n in NSTR[:-1]], "nref_sw": nsw, "nref_lw": nlw}, f, indent=1)
    sys.exit(ck.done("check_ch05_convergence"))


if __name__ == "__main__":
    main()
