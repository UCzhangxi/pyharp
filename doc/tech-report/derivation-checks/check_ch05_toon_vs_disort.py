"""ch05: pyharp's Toon89 against converged DISORT on the ch05 grid, with the error split into a numerical part and
a two-stream approximation part.

Shortwave. The numerical error is Toon minus the exact solution of the ODE Toon discretises: the quadrature
closure with delta-Eddington scaling and a Lambertian surface, as in toon_mckay89_shortwave (pyharp at the code
pin), for a homogeneous slab,

    dF+/dtau =  g1 F+ - g2 F- - g3 w' F0 exp(-tau'/mu0),
    dF-/dtau =  g2 F+ - g1 F- + g4 w' F0 exp(-tau'/mu0),
    F-(0) = 0,  F+(tau0') = A_s (F-(tau0') + mu0 F0 exp(-tau0'/mu0)),

solved here independently by shooting with the 3 x 3 matrix exponential in 50-digit arithmetic (mpmath), so the
growing mode exp(+lambda tau) costs no accuracy. The approximation error is that exact solution minus DISORT at
N_ref = 64 streams (check_ch05_convergence [C6]); the total error is Toon minus DISORT.
Thermal. Toon's source-function technique is not a plain two-stream ODE; its numerical part is bounded by the
multi-layer invariance of a homogeneous isothermal slab and by the agreement of the band Planck integrals, and the
total error is Toon minus DISORT at N_ref = 32 (check_ch05_convergence [C13]).

Errors: abs = |dF| / F_inc (shortwave mu0 F0; thermal pi B_band(300 K)); frac = |dF| / |F_ref| on fluxes with
F_ref >= 1 % of F_inc (the fractional error of Toon et al. 1989, p. 16,294, restricted as their text restricts it).

Run: python3 check_ch05_toon_vs_disort.py [--data DIR]  (about 10 s). Exit status: the number of FAIL lines.
"""

import argparse
import json
import os
import sys

import mpmath as mp
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch05_common as C  # noqa: E402

mp.mp.dps = 50
NREF_SW, NREF_LW = 64, 32
FLOOR = 0.01


def exact_sw(tau, ssa, g, mu0, albedo, fracs):
    """Exact solution of Toon's shortwave ODE (quadrature closure, delta-Eddington) for a homogeneous slab, F0 = 1;
    returns (F+, F- + F_dir) at optical-depth fractions `fracs` from the top. Mirrors the coefficient lines of
    toon_mckay89_shortwave: w0, dtau, hg (delta scaling); g1, g2, g3, g4 (quadrature closure)."""
    w = mp.mpf((1 - g * g) * ssa) / mp.mpf(1 - ssa * g * g)
    t0 = mp.mpf(1 - ssa * g * g) * mp.mpf(tau)
    hg = mp.mpf(g) / (1 + mp.mpf(g))
    s3 = mp.sqrt(3)
    g1 = s3 / 2 * (2 - w * (1 + hg))
    g2 = s3 / 2 * w * (1 - hg)
    mu = mp.mpf(mu0)
    g3 = (1 - s3 * hg * mu) / 2
    g4 = 1 - g3
    M = mp.matrix([[g1, -g2, -g3 * w], [g2, -g1, g4 * w], [0, 0, -1 / mu]])
    P = mp.expm(M * t0)
    a = mp.mpf(albedo)
    x = -(P[0, 2] - a * P[1, 2] - a * mu * P[2, 2]) / (P[0, 0] - a * P[1, 0])
    out = []
    for f in fracs:
        v = mp.expm(M * t0 * mp.mpf(f)) * mp.matrix([x, 0, 1])
        out.append((float(v[0]), float(v[1] + mu * v[2])))
    return np.array(out)


def stats(dif, ref):
    ab = np.abs(dif).ravel()
    r = np.abs(ref).ravel()
    m = r >= FLOOR
    fr = ab[m] / r[m]
    return {"n": int(ab.size), "abs_max": float(ab.max()), "abs_med": float(np.median(ab)), "n_frac": int(m.sum()),
            "frac_max": float(fr.max()), "frac_med": float(np.median(fr))}


def fmt(s):
    return (f"abs max {s['abs_max']:.2e} med {s['abs_med']:.2e}; frac max {s['frac_max']:.3f} "
            f"med {s['frac_med']:.2e}; n {s['n']}, n_frac {s['n_frac']}")


def sw_regimes(g):
    t, w, gg, mu, a = g["tau"], g["ssa"], g["g"], g["mu0"], g["albedo"]
    r = {"all omega<1": w < 1}
    for tl, tm in [("tau<=0.1", t <= 0.1), ("0.3<=tau<=1", (t >= 0.3) & (t <= 1)), ("tau>=3", t >= 3)]:
        for wl, wm in [("omega<=0.6", w <= 0.6), ("omega=0.9", w == 0.9), ("omega 0.99-0.999", (w >= 0.99) & (w < 1))]:
            r[f"{tl}, {wl}"] = tm & wm
    r["g=0"] = (gg == 0) & (w < 1)
    r["g>=0.5"] = (gg >= 0.5) & (w < 1)
    r["mu0=0.2"] = (mu == 0.2) & (w < 1)
    r["mu0>=0.5"] = (mu >= 0.5) & (w < 1)
    r["omega=1 exactly"] = w == 1
    return r


def lw_regimes(g):
    t, w, gg = g["tau"], g["ssa"], g["g"]
    r = {"all": np.ones_like(t, bool)}
    for tl, tm in [("tau<=0.1", t <= 0.1), ("0.3<=tau<=1", (t >= 0.3) & (t <= 1)), ("tau>=3", t >= 3)]:
        for wl, wm in [("omega=0", w == 0), ("omega 0.3-0.6", (w > 0) & (w <= 0.6)), ("omega 0.9-0.99", w >= 0.9)]:
            r[f"{tl}, {wl}"] = tm & wm
    r["g=0"] = gg == 0
    r["g>=0.5"] = gg >= 0.5
    return r


def test_toon_cases(ck):
    """The cases tests/test_toon.py runs, against 4-stream DISORT (as the test does) and against N_ref."""
    cases = [(0.1, 0.5), (0.5, 0.5), (0.9, 0.5), (0.5, 0.1), (0.5, 0.9)]
    w = np.array([c[0] for c in cases])
    g = np.array([c[1] for c in cases])
    n = len(cases)
    tau = np.full((n, 10), 0.1)
    toon = C.run_toon_sw(tau, C.same(w, 10), C.same(g, 10), np.full(n, 0.5), np.zeros(n))[:, 0, 1]
    out = {}
    for ns in [4, NREF_SW]:
        d = C.run_disort_sw(ns, tau, C.same(w, 10), np.repeat(C.hg_moments(g, ns)[:, None, :], 10, 1),
                            np.full(n, 0.5), np.zeros(n))[:, 0, 1]
        out[f"sw nstr={ns}"] = np.abs(toon - d) / d
    for lab, cs in [("lw iso omega=0", [(0.0, 0.0)]), ("lw scattering", cases)]:
        w = np.array([c[0] for c in cs])
        g = np.array([c[1] for c in cs])
        n = len(cs)
        tau = np.full((n, 10), 0.3)
        temf = np.full((n, 11), 300.0)
        for ns in [4, NREF_LW]:
            vals = []
            for lo, hi in [(500.0, 1000.0), (1000.0, 1500.0), (1500.0, 2000.0)]:
                t = C.run_toon_lw(tau, C.same(w, 10), C.same(g, 10), temf, np.zeros(n), lo, hi,
                                  extra_flags=())[:, -1, 0]
                d = C.run_disort_lw(ns, tau, C.same(w, 10), np.repeat(C.hg_moments(g, ns)[:, None, :], 10, 1),
                                    temf, np.zeros(n), lo, hi)[:, -1, 0]
                vals.extend(np.abs(t - d) / d)
            out[f"{lab} nstr={ns}"] = np.array(vals)
    for k, v in out.items():
        ck.info(f"test_toon.py cases, |Toon - DISORT|/DISORT, {k}", f"max {v.max():.3e}; "
                + " ".join(f"{x:.4f}" for x in v[:5]))
    return {k: float(v.max()) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    a = ap.parse_args()
    print(C.version_line())
    print(C.env_line())
    ck = C.Checker()
    data = {}
    # ---------------- shortwave
    g = C.sw_grid()
    n = len(g["tau"])
    ref = C.run_disort_sw(NREF_SW, C.layers(g["tau"], C.NLYR_SW), C.same(g["ssa"], C.NLYR_SW),
                          np.repeat(C.hg_moments(g["g"], NREF_SW)[:, None, :], C.NLYR_SW, 1), g["mu0"], g["albedo"])
    ref /= g["mu0"][:, None, None]
    toon = C.run_toon_sw(C.layers(g["tau"], C.NLYR_SW), C.same(g["ssa"], C.NLYR_SW), C.same(g["g"], C.NLYR_SW),
                         g["mu0"], g["albedo"]) / g["mu0"][:, None, None]
    fr = [1.0, 0.5, 0.0]           # bottom-up levels as fractions of tau0 from the top
    ex = np.array([exact_sw(*(g[k][i] for k in ["tau", "ssa", "g", "mu0", "albedo"]), fr) for i in range(n)])
    ex /= g["mu0"][:, None, None]
    w1 = g["ssa"] < 1
    num, app, tot = toon - ex, ex - ref, toon - ref
    ck.check("SW numerical error max |Toon - exact ODE|/F_inc, omega < 1 (720 columns)",
             float(np.abs(num[w1]).max()), 1e-12)
    ck.expect_fail("SW numerical error max |Toon - exact ODE|/F_inc, omega = 1 exactly (144 columns)",
                   float(np.abs(num[~w1]).max()), 1e-6)
    reg = sw_regimes(g)
    data["sw"] = {}
    for name, m in reg.items():
        s_num, s_app, s_tot = stats(num[m], ref[m]), stats(app[m], ref[m]), stats(tot[m], ref[m])
        data["sw"][name] = {"num": s_num, "app": s_app, "tot": s_tot}
        ck.info(f"SW total (Toon - DISORT), {name}", fmt(s_tot))
        if name != "omega=1 exactly":
            ck.info(f"SW approximation (exact ODE - DISORT), {name}", f"abs max {s_app['abs_max']:.2e}")
    bq = {"R": (tot[:, 2, 0], ref[:, 2, 0]), "T": (tot[:, 0, 1], ref[:, 0, 1])}
    acol_t = toon[:, 2, 1] - toon[:, 2, 0] - toon[:, 0, 1] + toon[:, 0, 0]
    acol_r = ref[:, 2, 1] - ref[:, 2, 0] - ref[:, 0, 1] + ref[:, 0, 0]
    bq["A_col"] = (acol_t - acol_r, acol_r)
    for k, (d, r) in bq.items():
        ck.info(f"SW boundary quantity {k}, omega < 1", fmt(stats(d[w1], r[w1])))
    fe = np.where(np.abs(ref) >= FLOOR, np.abs(tot) / np.abs(ref), 0.0)
    fe[~w1] = 0.0
    big = fe > 0.10
    nfl = int((np.abs(ref[w1]) >= FLOOR).sum())
    ck.info("SW fluxes >= 1 % of F_inc with frac error > 10 %",
            f"{int(big.sum())} of {nfl}; upward {int(big[..., 0].sum())}, at mu0 = 0.2 {int(big[g['mu0'] == 0.2].sum())}")
    i, l, c = np.unravel_index(int(np.argmax(fe)), fe.shape)
    ck.info("SW worst frac error", f"{fe[i, l, c]:.3f} on {'F+' if c == 0 else 'F- + F_dir'} = {ref[i, l, c]:.4f} "
            f"F_inc at {['surface', 'middle', 'top'][l]}; " + ", ".join(f"{k}={g[k][i]:g}" for k in g))
    data["sw_frac_gt10"] = [int(big.sum()), nfl]
    # ---------------- thermal
    gl = C.lw_grid()
    nl = len(gl["tau"])
    norm = C.band_planck_flux(C.T_BOT, C.WAVE_LO, C.WAVE_HI)
    taul = C.layers(gl["tau"], C.NLYR_LW)
    refl = C.run_disort_lw(NREF_LW, taul, C.same(gl["ssa"], C.NLYR_LW),
                           np.repeat(C.hg_moments(gl["g"], NREF_LW)[:, None, :], C.NLYR_LW, 1), C.lw_temf(nl),
                           gl["albedo"], C.WAVE_LO, C.WAVE_HI) / norm
    data["lw"] = {}
    for lab, flags in [("hard_surface", ("hard_surface",)),
                       ("hard_surface + delta_eddington_lw", ("hard_surface", "delta_eddington_lw"))]:
        t = C.run_toon_lw(taul, C.same(gl["ssa"], C.NLYR_LW), C.same(gl["g"], C.NLYR_LW), C.lw_temf(nl),
                          gl["albedo"], C.WAVE_LO, C.WAVE_HI, extra_flags=flags) / norm
        data["lw"][lab] = {}
        for name, m in lw_regimes(gl).items():
            s = stats((t - refl)[m], refl[m])
            data["lw"][lab][name] = s
            ck.info(f"LW total (Toon {lab} - DISORT), {name}", fmt(s))
    iso = np.array([0.1, 1.0, 10.0])
    k = len(iso)
    pb = C.band_planck_flux(250.0, C.WAVE_LO, C.WAVE_HI)
    for w, gg in [(0.0, 0.0), (0.6, 0.5), (0.9, 0.85)]:
        one = C.run_toon_lw(iso[:, None], np.full((k, 1), w), np.full((k, 1), gg), np.full((k, 2), 250.0),
                            np.zeros(k), C.WAVE_LO, C.WAVE_HI)
        many = C.run_toon_lw(np.repeat(iso[:, None] / 16, 16, 1), np.full((k, 16), w), np.full((k, 16), gg),
                             np.full((k, 17), 250.0), np.zeros(k), C.WAVE_LO, C.WAVE_HI)
        ck.check(f"LW multi-layer invariance, isothermal slab omega={w} g={gg}: 1 vs 16 layers, boundary fluxes/piB",
                 float(np.abs(one[:, [0, -1]] - many[:, [0, -1]]).max() / pb), 1e-10)
    for T in [200.0, 300.0]:
        t = C.run_toon_lw(np.array([[50.0]]), np.zeros((1, 1)), np.zeros((1, 1)), np.full((1, 2), T), np.zeros(1),
                          C.WAVE_LO, C.WAVE_HI)
        d = C.run_disort_lw(NREF_LW, np.array([[50.0]]), np.zeros((1, 1)), np.zeros((1, 1, NREF_LW)),
                            np.full((1, 2), T), np.zeros(1), C.WAVE_LO, C.WAVE_HI)
        ck.check(f"LW Planck integrals, opaque isothermal slab {T:.0f} K: |Toon up_TOA - DISORT up_TOA|/piB",
                 abs(t[0, -1, 0] - d[0, -1, 0]) / C.band_planck_flux(T, C.WAVE_LO, C.WAVE_HI), 1e-5)
    data["test_toon"] = test_toon_cases(ck)
    if a.data:
        os.makedirs(a.data, exist_ok=True)
        with open(os.path.join(a.data, "toon_vs_disort.json"), "w") as f:
            json.dump(data, f, indent=1)
    sys.exit(ck.done("check_ch05_toon_vs_disort"))


if __name__ == "__main__":
    main()
