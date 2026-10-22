"""ch02 check: energy identities of the two-stream equations, and where their closed-form solution degenerates.

Two-stream system (Toon et al. 1989, JGR 94, 16287, doi:10.1029/jd094id13p16287, eqs. 11-14; Meador & Weaver 1980,
eqs. 12-13), tau counted downward from the top, F0 the beam flux normal to the beam (Toon's pi F_s):
    dF+/dtau = g1 F+ - g2 F- - g3 w F0 exp(-tau/mu0),     dF-/dtau = g2 F+ - g1 F- + g4 w F0 exp(-tau/mu0).
Net flux including the direct beam: Fnet = F+ - F- - mu0 F0 exp(-tau/mu0).
C1-C6: identities, symbolic (sympy). C7-C10: the omega = 1 limit of the closed form (Toon eqs. 19-24) and of the
tridiagonal matrix the shortwave kernel assembles (toon_mckay89_shortwave in
src/rtsolver/toon_mckay89_shortwave_impl.h at the code pin, mirrored for two layers and a black surface in C9).
C11-C19: a 40-digit mpmath solution of the ODE for one delta-scaled layer with the quadrature closure.

Mirrors pyharp at the code pin (code_pin.yml) only in C9 and C10. Needs numpy and sympy (mpmath ships with sympy).
Run: python3 check_ch02_conservation.py   (any directory; exits with the number of failed claims)
"""

import sys

import mpmath as mp
import numpy as np
import sympy as sp

w, g, mu0, mu1 = sp.symbols("omega g mu0 mu1", positive=True)
tau, F0, Fp, Fm, B0, B1 = sp.symbols("tau F0 Fp Fm B0 B1")
G1, G2, G3, G4 = sp.symbols("gamma1 gamma2 gamma3 gamma4")
r3 = sp.sqrt(3)
QUAD = (r3 * (2 - w * (1 + g)) / 2, w * r3 * (1 - g) / 2)   # Toon Table 1, quadrature (pyharp shortwave)
HM = (2 - w * (1 + g), w * (1 - g))                          # Toon Table 1, hemispheric mean (pyharp longwave)
E = sp.exp(-tau / mu0)


def report(n, ok, label, detail):
    print(f"[C{n}] {'PASS' if ok else 'FAIL'} {label}: {detail}")
    return bool(ok)


def check_C1_C2_net_flux():
    dnet = sp.expand((G1 * Fp - G2 * Fm - G3 * w * F0 * E) - (G2 * Fp - G1 * Fm + G4 * w * F0 * E) + F0 * E)
    ref = sp.expand((G1 - G2) * (Fp + Fm) + (1 - w * (G3 + G4)) * F0 * E)
    cons = sp.simplify(ref.subs({G2: G1, G4: 1 - G3, w: 1}))
    return [report(1, sp.simplify(dnet - ref) == 0, "dFnet/dtau = (g1-g2)(F+ + F-) + (1 - w(g3+g4)) F0 e^{-tau/mu0}",
                   "identity for arbitrary gammas (Toon eq. 28)"),
            report(2, cons == 0, "conservative layer", f"with g1 = g2, g3 + g4 = 1, w = 1: dFnet/dtau = {cons}")]


def check_C3_C4_absorption():
    Jd = (Fp + Fm) / (4 * sp.pi * mu1)                     # Toon eq. (17)
    Jb = F0 * E / (4 * sp.pi)
    beam = sp.expand(((G1 - G2) * (Fp + Fm) + (1 - w) * F0 * E).subs(G1, G2 + (1 - w) / mu1))
    Bt = B0 + B1 * tau
    S = 2 * sp.pi * (1 - w) * Bt                           # Toon eq. (15)
    therm = sp.expand(((G1 * Fp - G2 * Fm - S) - (G2 * Fp - G1 * Fm + S)).subs(G1, G2 + (1 - w) / mu1))
    return [report(3, sp.simplify(beam - (1 - w) * 4 * sp.pi * (Jd + Jb)) == 0, "beam: dFnet/dtau = (1-w) 4 pi J",
                   "J = diffuse + direct mean intensity, g1 - g2 = (1-w)/mu1 (Toon eqs. 17, 18)"),
            report(4, sp.simplify(therm - (1 - w) * 4 * sp.pi * (Jd - Bt)) == 0, "thermal: dFnet/dtau = (1-w) 4 pi (J - B)",
                   "S+- = 2 pi (1-w) B (Toon eq. 15)")]


def check_C5_C6_particular():
    S = 2 * sp.pi * (1 - w) * (B0 + B1 * tau)
    Cp = 2 * sp.pi * mu1 * (B0 + B1 * (tau + 1 / (G1 + G2)))
    Cm = 2 * sp.pi * mu1 * (B0 + B1 * (tau - 1 / (G1 + G2)))
    sub = {G1: G2 + (1 - w) / mu1}
    r1 = [sp.simplify((sp.diff(Cp, tau) - (G1 * Cp - G2 * Cm - S)).subs(sub)),
          sp.simplify((sp.diff(Cm, tau) - (G2 * Cp - G1 * Cm + S)).subs(sub))]
    lam2 = G1**2 - G2**2
    Ap = w * F0 * E * ((G1 - 1 / mu0) * G3 + G4 * G2) / (lam2 - 1 / mu0**2)
    Am = w * F0 * E * ((G1 + 1 / mu0) * G4 + G2 * G3) / (lam2 - 1 / mu0**2)
    r2 = [sp.simplify(sp.diff(Ap, tau) - (G1 * Ap - G2 * Am - G3 * w * F0 * E)),
          sp.simplify(sp.diff(Am, tau) - (G2 * Ap - G1 * Am + G4 * w * F0 * E))]
    return [report(5, r1 == [0, 0], "Toon eq. 27 C+- solves the thermal ODE", f"residuals {r1}"),
            report(6, r2 == [0, 0], "Toon eqs. 23-24 C+- solve the beam ODE", f"residuals {r2}")]


def check_C7_lambda_gamma():
    eps = sp.Symbol("epsilon", positive=True)
    out = []
    for nm, (a, b) in (("quadrature", QUAD), ("hemispheric mean", HM)):
        L = sp.sqrt(a**2 - b**2)
        l1, G1v = sp.simplify(L.subs(w, 1)), sp.simplify(((a - L) / b).subs(w, 1))
        lead = sp.simplify(sp.series(L.subs(w, 1 - eps), eps, 0, 1).removeO())
        out.append((nm, l1, G1v, lead))
    ok = all(x[1] == 0 and x[2] == 1 for x in out)
    return report(7, ok, "lambda = 0 and Gamma = 1 at w = 1",
                  "; ".join(f"{a}: lambda(1 - eps) ~ {d}" for a, _, _, d in out))


def check_C8_basis():
    Gm, c, d, gg = sp.symbols("Gamma c d gamma")
    det = sp.Matrix([[1, Gm], [Gm, 1]]).det()
    Fpl, Fml = gg * c * tau + (d + c) / 2, gg * c * tau + (d - c) / 2   # solves g1 = g2 = gamma
    res = [sp.simplify(sp.diff(Fpl, tau) - gg * (Fpl - Fml)), sp.simplify(sp.diff(Fml, tau) - gg * (Fpl - Fml))]
    return report(8, det.subs(Gm, 1) == 0 and res == [0, 0], "Toon basis collapses at Gamma = 1",
                  f"det = {det}; the missing solution F+ - F- = c, F+ + F- = 2 gamma c tau + d solves the ODE")


def check_C9_tridiagonal():
    """Rows of the matrix assembled in toon_mckay89_shortwave (top row, interface rows, bottom row, albedo 0)."""
    G0, Gb, e = sp.symbols("Gamma0 Gamma1 e", positive=True)

    def E14(Gx, Ep):
        return Ep + Gx / Ep, Ep - Gx / Ep, Gx * Ep + 1 / Ep, Gx * Ep - 1 / Ep
    E1, E2, E3, E4 = E14(G0, e)
    F1, F2, _, _ = E14(Gb, e)
    M = sp.Matrix([[G0 + 1, G0 - 1, 0, 0],
                   [(E1 + E3) * (Gb - 1), (E2 + E4) * (Gb - 1), 2 * (1 - Gb**2), 0],
                   [0, 2 * (1 - G0**2), (E1 - E3) * (1 + Gb), (E1 + E3) * (Gb - 1)],
                   [0, 0, F1, F2]])
    det = sp.simplify(M.det())
    d1 = sp.simplify(det.subs({G0: 1, Gb: 1, e: 1}))
    dx = sp.simplify(det.subs({G0: sp.Rational(1, 2), Gb: sp.Rational(1, 2), e: 2}))
    return report(9, d1 == 0 and dx != 0, "2-layer shortwave tridiagonal is singular at Gamma = 1, e^{lambda dtau} = 1",
                  f"det = {d1} there; {dx} at Gamma = 1/2, e = 2")


def check_C10_float64():
    """numpy transliteration of the shortwave scaling and gammas at W = 1 exactly (no FMA; round-off dependent)."""
    gg = np.linspace(0.0, 0.99, 100001)
    gsq = gg * gg
    w0 = ((1.0 - gsq) * 1.0) / (1.0 - 1.0 * gsq)
    hg = gg / (1.0 + gg)
    s = np.sqrt(3.0) / 2.0
    disc = (s * (2.0 - w0 * (1.0 + hg)))**2 - ((s * w0) * (1.0 - hg))**2
    lam = np.sqrt(np.where(disc > 0, disc, 0.0))
    ok = bool(np.all(w0 == 1.0)) and float(lam.max()) < 1e-7
    return report(10, ok, "float64 at W = 1: scaled w is exactly 1 and lambda is round-off",
                  f"NaN (disc < 0) {np.mean(disc < 0):.3f}, zero {np.mean(disc == 0):.3f}, positive "
                  f"{np.mean(disc > 0):.3f} of 100001 g in [0, 0.99]; max lambda below 1e-7")


# ---------------- mpmath solution of one delta-scaled layer, quadrature closure ----------------
mp.mp.dps = 40


def gam_q(wv, gv, m0):
    s3 = mp.sqrt(3)
    g3 = (1 - s3 * gv * m0) / 2
    return s3 * (2 - wv * (1 + gv)) / 2, wv * s3 * (1 - gv) / 2, g3, 1 - g3


def dscale(tv, wv, gv):  # Wiscombe 1977 eqs. (14), (15), (20) with f = g^2
    return (1 - wv * gv**2) * tv, (1 - gv**2) * wv / (1 - wv * gv**2), gv / (1 + gv)


def solve_ode(tv, wv, gv, m0, As):
    ts, ws, gs = dscale(tv, wv, gv)
    g1, g2, g3, g4 = gam_q(ws, gs, m0)
    ya = mp.odefun(lambda t, y: [g1 * y[0] - g2 * y[1] - g3 * ws * mp.exp(-t / m0),
                                 g2 * y[0] - g1 * y[1] + g4 * ws * mp.exp(-t / m0)], 0, [mp.mpf(0), mp.mpf(0)])
    yb = mp.odefun(lambda t, y: [g1 * y[0] - g2 * y[1], g2 * y[0] - g1 * y[1]], 0, [mp.mpf(1), mp.mpf(0)])
    a, b = ya(ts), yb(ts)
    x = (As * (a[1] + m0 * mp.exp(-ts / m0)) - a[0]) / (b[0] - As * b[1])   # F-(0) = 0; Lambertian bottom
    return (lambda t: (ya(t)[0] + x * yb(t)[0], ya(t)[1] + x * yb(t)[1])), ts, ws, (g1, g2, g3, g4)


def closed_form(tv, wv, gv, m0, As):
    """Toon eqs. (19)-(24) for one layer with the same boundary conditions; returns F+(0) and det."""
    ts, ws, gs = dscale(tv, wv, gv)
    g1, g2, g3, g4 = gam_q(ws, gs, m0)
    L = mp.sqrt(g1**2 - g2**2)
    Gm = (g1 - L) / g2
    Ap = ws * ((g1 - 1 / m0) * g3 + g4 * g2) / (L**2 - 1 / m0**2)
    Am = ws * ((g1 + 1 / m0) * g4 + g2 * g3) / (L**2 - 1 / m0**2)
    ex = mp.exp(-ts / m0)
    A = mp.matrix([[Gm, 1], [mp.exp(L * ts) * (1 - As * Gm), mp.exp(-L * ts) * (Gm - As)]])
    k = mp.lu_solve(A, mp.matrix([-Am, As * (Am + m0) * ex - Ap * ex]))
    return k[0] + Gm * k[1] + Ap, mp.det(A)


def fnet(F, t, m0):
    v = F(t)
    return v[0] - v[1] - m0 * mp.exp(-t / m0)


def check_numeric():
    res = []
    for n, (tv, gv, m0, As) in ((11, ("1", "0.75", "0.5", "0")), (15, ("5", "0.5", "0.866", "0.3"))):
        tv, gv, m0, As = map(mp.mpf, (tv, gv, m0, As))
        F, ts, _, _ = solve_ode(tv, mp.mpf(1), gv, m0, As)
        fn = [fnet(F, ts * k / 20, m0) for k in range(21)]
        spread = max(fn) - min(fn)
        res.append(report(n, spread < mp.mpf("1e-30"), f"w = 1, tau = {tv}, g = {gv}, mu0 = {m0}, A_s = {As}:"
                          " Fnet constant over 21 levels", "max - min below 1e-30 (40 digits)"))
        if As == 0:
            g1, _, g3, _ = gam_q(mp.mpf(1), gv / (1 + gv), m0)
            Rmw = (g1 * ts + (g3 - g1 * m0) * (1 - mp.exp(-ts / m0))) / (1 + g1 * ts)   # MW eq. (24)
            R, T = F(0)[0] / m0, (F(ts)[1] + m0 * mp.exp(-ts / m0)) / m0
            res.append(report(12, abs(R - Rmw) < mp.mpf("1e-30") and abs(R + T - 1) < mp.mpf("1e-30"),
                              "R(w = 1) = MW eq. 24 and R + T = 1", f"R = {mp.nstr(R, 15)}; both residuals below 1e-30"))
            conv = [(k, closed_form(tv, 1 - mp.mpf(10)**(-k), gv, m0, As)[0] / m0 - Rmw) for k in (4, 8, 12, 16, 24)]
            _, det1 = closed_form(tv, mp.mpf(1), gv, m0, As)
            res.append(report(13, abs(conv[-1][1]) < mp.mpf("1e-23") and abs(det1) < mp.mpf("1e-15"),
                              "closed form: R(1 - 10^-k) -> R(1); singular at w = 1",
                              ", ".join(f"k={k}: {mp.nstr(abs(e), 2)}" for k, e in conv) + "; |det| at w = 1 below 1e-15"))
            with mp.workprec(53):
                sweep = [(k, abs(closed_form(tv, 1 - mp.mpf(10)**(-k), gv, m0, As)[0] / m0 - Rmw))
                         for k in (8, 10, 12, 14, 16)]
            best = min(sweep, key=lambda x: x[1])[0]
            res.append(report(14, best == 12, "53-bit closed form: error vs 1 - w = 10^-k is smallest at k = 12",
                              ", ".join(f"k={k}: {mp.nstr(e, 2)}" for k, e in sweep)))
    for n, (tv, wv, gv, m0, As) in ((16, ("0.3", "0.9", "0.85", "0.2", "0")), (18, ("2", "0.5", "0.3", "1", "0.3"))):
        tv, wv, gv, m0, As = map(mp.mpf, (tv, wv, gv, m0, As))
        F, ts, ws, _ = solve_ode(tv, wv, gv, m0, As)
        jump = fnet(F, ts, m0) - fnet(F, 0, m0)
        absorbed = mp.quad(lambda t: (1 - ws) * ((F(t)[0] + F(t)[1]) * mp.sqrt(3) + mp.exp(-t / m0)), [0, ts])
        res.append(report(n, abs(jump - absorbed) < mp.mpf("1e-30"), f"w = {wv}, tau = {tv}, g = {gv}, mu0 = {m0},"
                          f" A_s = {As}: Fnet jump = integrated absorption", f"{mp.nstr(jump, 15)}; diff below 1e-30"))
        Fp0, _ = closed_form(tv, wv, gv, m0, As)
        res.append(report(n + 1, abs(Fp0 - F(0)[0]) < mp.mpf("1e-30"), f"closed form = ODE, F+(0), w = {wv}",
                          "diff below 1e-30"))
    return res


def main():
    res = check_C1_C2_net_flux() + check_C3_C4_absorption() + check_C5_C6_particular()
    res += [check_C7_lambda_gamma(), check_C8_basis(), check_C9_tridiagonal(), check_C10_float64()]
    res += check_numeric()
    nfail = res.count(False)
    print(f"check_ch02_conservation: {len(res) - nfail} of {len(res)} claims pass")
    return nfail


if __name__ == "__main__":
    sys.exit(main())
