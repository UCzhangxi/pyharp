"""ch05: analytic cases for Toon89 and DISORT.

A. Beer-Lambert direct beam (omega = 0, black surface, 5 unequal layers): F^- + F_dir = mu0 F0 exp(-tau/mu0) and
   F^+ = 0. With a Lambertian surface of albedo A_s = 0.4 the downward flux is still the beam alone, the surface
   reflects A_s times it, and the exact upward flux at the top is A_s F_dir(tau0) 2 E3(tau0).
B. Grey isothermal slab (omega = 0, T = 250 K, no incoming radiation at the top): the downward flux at the bottom
   is pi B (1 - 2 E3(tau0)); over a black surface at the same temperature the upward flux at the top is pi B.
C. Energy closure. (i) omega = 1: the net flux is the same at every level. (ii) omega < 1: the column absorption
   from the net-flux drop equals the integral of (1 - omega) 4 pi Jbar over tau, Jbar from DISORT's mean intensity
   (`gather_flx`, channel 4), Simpson's rule on 400 layers; reflected + column-absorbed + surface-absorbed = 1.

Run: python3 check_ch05_analytic.py [--data DIR]. Exit status: the number of FAIL lines.
"""

import argparse
import itertools
import json
import os
import sys

import numpy as np
import torch
from scipy.integrate import simpson
from scipy.special import expn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch05_common as C  # noqa: E402

NREF = 64
WLO, WHI = 500.0, 1000.0
ABSCUT = 10.0   # cdisort's lyrcut threshold on the absorption optical depth (multi-layer, solar runs)


def part_a(ck):
    T, M = np.meshgrid([0.01, 0.1, 1.0, 3.0, 10.0, 30.0], [0.1, 0.2, 0.5, 1.0], indexing="ij")
    T, M = T.ravel(), M.ravel()
    n = len(T)
    tau = T[:, None] * np.array([0.1, 0.3, 0.05, 0.25, 0.3])[None, :]
    cum = np.concatenate([np.zeros((n, 1)), np.cumsum(tau, 1)], 1)          # top-down level depths
    exact = M[:, None] * np.exp(-cum / M[:, None])
    for alb in [0.0, 0.4]:
        a = np.full(n, alb)
        runs = {"Toon": C.run_toon_sw(tau, np.zeros_like(tau), np.zeros_like(tau), M, a),
                f"DISORT nstr={NREF}": C.run_disort_sw(NREF, tau, np.zeros_like(tau), np.zeros((n, 5, NREF)), M, a)}
        for name, f in runs.items():
            dn, up = f[:, ::-1, 1], f[:, ::-1, 0]
            m = exact > 1e-10 * M[:, None]       # cdisort drops a beam below ~1e-12 of incident
            if name.startswith("DISORT"):
                below = (cum >= ABSCUT) & (T[:, None] >= ABSCUT)
                lost = (np.abs(dn - exact) / M[:, None])[below]
                ck.check(f"A albedo={alb} {name}: |dn - exact|/F_inc below tau = {ABSCUT:g} (lyrcut bound "
                         f"exp(-{ABSCUT:g}))", float(lost.max()), np.exp(-ABSCUT) * 1.0001)
                m &= ~below
            ck.check(f"A albedo={alb} {name}: max rel err of dn", float((np.abs(dn - exact)[m] / exact[m]).max()),
                     1e-12)
            if alb == 0.0:
                ck.check(f"A albedo=0 {name}: max |up|/F_inc", float(np.abs(up / M[:, None]).max()), 1e-14)
                continue
            d = np.abs(up[:, -1] - alb * dn[:, -1]) / M
            cut = T >= ABSCUT
            ck.check(f"A albedo=0.4 {name}: |up_s - A_s dn_s|/F_inc, tau0 < {ABSCUT:g}", float(d[~cut].max()), 1e-12)
            ck.check(f"A albedo=0.4 {name}: |up_s - A_s dn_s|/F_inc, tau0 >= {ABSCUT:g} (bound A_s exp(-{ABSCUT:g}))",
                     float(d[cut].max()), alb * np.exp(-ABSCUT) * 1.0001)
            e = float((np.abs(up[:, 0] - alb * exact[:, -1] * 2 * expn(3, T)) / M).max())
            if name.startswith("DISORT"):
                ck.check(f"A albedo=0.4 {name}: |up_TOA - A_s F_dir(tau0) 2E3(tau0)|/F_inc", e, 1e-4)
            else:
                ck.info("A albedo=0.4 Toon: |up_TOA - A_s F_dir(tau0) 2E3(tau0)|/F_inc",
                        f"{e:.3e} (two-stream treatment of the reflected diffuse field)")


def part_b(ck, data):
    taus = np.array([0.01, 0.1, 0.3, 1.0, 3.0, 10.0])
    n = len(taus)
    piB = C.band_planck_flux(250.0, WLO, WHI)
    temf = np.full((n, 6), 250.0)
    tau = np.repeat(taus[:, None] / 5, 5, 1)
    exact = piB * (1 - 2 * expn(3, taus))
    runs = {"Toon": C.run_toon_lw(tau, np.zeros_like(tau), np.zeros_like(tau), temf, np.zeros(n), WLO, WHI)}
    for ns in [4, 16, NREF]:
        runs[f"DISORT nstr={ns}"] = C.run_disort_lw(ns, tau, np.zeros_like(tau), np.zeros((n, 5, ns)), temf,
                                                    np.zeros(n), WLO, WHI)
    data["e3"] = {"tau": taus.tolist()}
    for name, f in runs.items():
        e = (f[:, 0, 1] - exact) / piB
        data["e3"][name] = e.tolist()
        line = " ".join(f"{x:+.2e}" for x in e)
        if name == f"DISORT nstr={NREF}":
            ck.check(f"B E3 slab {name}: max |dn_s - piB(1 - 2E3)|/piB", float(np.abs(e).max()), 1e-4)
        else:
            ck.info(f"B E3 slab {name}: (dn_s - piB(1 - 2E3))/piB at tau0 = 0.01 ... 10", line)
        ck.check(f"B isothermal over a black surface {name}: |up_TOA - piB|/piB",
                 float(np.abs(f[:, -1, 0] - piB).max() / piB), 1e-5)


def disort_full(nstr, tau, ssa, g, mu0, alb):
    """DISORT fluxes and mean intensity through gather_flx (CPU), levels bottom-up."""
    ncol, nlyr = tau.shape
    ds = C.make_disort(nstr, nlyr, ncol)
    prop = C._prop(tau, ssa, C.hg_moments(g, nstr))
    ds(torch.tensor(prop), fbeam=torch.ones(1, ncol, dtype=torch.float64),
       umu0=torch.tensor(mu0, dtype=torch.float64), albedo=torch.tensor(alb, dtype=torch.float64).view(1, ncol))
    return ds.gather_flx()[0].numpy()    # (ncol, nlvl, 8): rfldir, rfldn, flup, dfdt, uavg, ...


def part_c(ck):
    a = np.array(list(itertools.product([0.1, 1.0, 10.0], [0.3, 0.9, 1.0], [0.0, 0.85], [0.2, 1.0], [0.0, 0.4])))
    tau_t, w, g, mu, alb = a.T
    n, nl = len(a), 400
    full = disort_full(32, np.repeat(tau_t[:, None] / nl, nl, 1), np.repeat(w[:, None], nl, 1),
                       np.repeat(g[:, None], nl, 1), mu, alb)
    dn, up, jbar = full[..., 0] + full[..., 1], full[..., 2], full[..., 4]
    net = dn - up
    cons = w == 1
    ck.check("C(i) DISORT nstr=32, omega = 1: max |F_net(z) - F_net(TOA)|/F_inc",
             float((np.abs(net - net[:, -1:]).max(1) / mu)[cons].max()), 1e-6)
    ck.check("C DISORT surface balance |up_s - A_s dn_s|/F_inc (400 layers)",
             float((np.abs(up[:, 0] - alb * dn[:, 0]) / mu).max()), 1e-8)
    acol = (net[:, -1] - net[:, 0]) / mu
    z = np.linspace(0, 1, nl + 1)[None, :] * tau_t[:, None]
    src = (1 - w)[:, None] * 4 * np.pi * jbar
    aint = np.array([simpson(src[i][::-1], x=z[i]) for i in range(n)]) / mu
    ck.check("C(ii) DISORT nstr=32, omega < 1: |A_col - int (1 - omega) 4 pi Jbar dtau|/F_inc",
             float(np.abs(acol - aint)[~cons].max()), 1e-4)
    closure = (up[:, -1] + (net[:, -1] - net[:, 0]) + (dn[:, 0] - up[:, 0])) / mu
    ck.check("C DISORT R + A_col + A_surface = 1: max |sum - 1|", float(np.abs(closure - 1).max()), 1e-8)
    ck.check("C DISORT A_col/F_inc >= 0 (min, omega < 1)", float(acol[~cons].min()), -1e-10, cmp=">=")
    nlt = 10
    taut = np.repeat(tau_t[:, None] / nlt, nlt, 1)
    R = {}
    for lab, margin in [("omega = 1 exactly", 0.0), ("omega = 1 - 1e-12", 1e-12)]:
        wt = np.where(cons, 1 - margin, w)
        f = C.run_toon_sw(taut, np.repeat(wt[:, None], nlt, 1), np.repeat(g[:, None], nlt, 1), mu, alb)
        netT = f[..., 1] - f[..., 0]
        ck.check(f"C(i) Toon {lab}: max |F_net(z) - F_net(TOA)|/F_inc",
                 float((np.abs(netT - netT[:, -1:]).max(1) / mu)[cons].max()), 1e-6)
        R[margin] = f[cons, -1, 0] / mu[cons]
    ck.expect_fail("C Toon reflectance, omega = 1 exactly vs omega = 1 - 1e-12: max |dR|",
                   float(np.abs(R[0.0] - R[1e-12]).max()), 1e-6)
    ck.check("C Toon surface balance |up_s - A_s dn_s|/F_inc (omega = 1 - 1e-12 run)",
             float((np.abs(f[:, 0, 0] - alb * f[:, 0, 1]) / mu).max()), 1e-9)
    accT = (f[:, -1, 1] - f[:, -1, 0] - f[:, 0, 1] + f[:, 0, 0]) / mu
    ck.check("C Toon A_col/F_inc >= 0 (min, omega < 1)", float(accT[~cons].min()), -1e-12, cmp=">=")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    a = ap.parse_args()
    print(C.version_line())
    print(C.env_line())
    ck = C.Checker()
    data = {}
    part_a(ck)
    part_b(ck, data)
    part_c(ck)
    if a.data:
        os.makedirs(a.data, exist_ok=True)
        with open(os.path.join(a.data, "analytic.json"), "w") as f:
            json.dump(data, f, indent=1)
    sys.exit(ck.done("check_ch05_analytic"))


if __name__ == "__main__":
    main()
