#!/usr/bin/env python3
"""Check of the longwave two-stream source-function derivation of chapter 4 (scheme file `_longwave.qmd`).

Mirrors the formulas of `toon_mckay89_longwave` in src/rtsolver/toon_mckay89_longwave_impl.h of pyharp at the
pin of code_pin.yml (Toon et al. 1989 Table 1 hemispheric-mean row, eqs. 21-22, 25-27, Table 3).

  [C1] The code's auxiliary a = sqrt((1-w)/(1-w g)) gives Toon's hemispheric-mean lambda and Gamma:
       lambda = a (1 - w g)/mu1 = sqrt(gamma1^2 - gamma2^2) and Gamma = (1 - a)/(1 + a) = gamma2/(gamma1 + lambda),
       with mu1 = 1/2 (sympy).
  [C2] `term` = mu1/(1 - w g) = 1/(gamma1 + gamma2) (Toon eq. 27), and the Table 3 coefficient
       1/(gamma1 + gamma2) - mu1 equals the code's mu1 w g/(1 - w g) (sympy).
  [C3] The five angles `uarr` and weights `wuarr` are the 5-point Gauss rule for the weight mu on [0, 1]
       (computed here by Golub-Welsch in numpy): nodes and weights agree to 1e-10 (the code stores 10 decimals), the weights sum to 1/2, and
       the rule integrates mu^k mu exactly for k <= 9 (to 1e-10, the 10 digits the code stores).
  [C4] Isothermal column (B1 = 0, B0 = B in every layer, B_top = B, hard surface emitting (1 - A_s) B):
       every right-hand side of the tridiagonal system vanishes, so the homogeneous amplitudes vanish and
       F+ = F- = pi B (sympy, two layers, symbolic A_s).
  [C5] Same column with the non-hard surface (bottom value B + B1 mu1, albedo A_s kept in the bottom row):
       the bottom right-hand side is A_s B, nonzero for A_s > 0 (sympy).
  [C6] Hemispheric-mean source function: inserting the layer solution into
       2 pi S^+ = w[(1+g)F^+ + (1-g)F^-] + 2 pi (1-w) B gives the code's G = `g[n]`, H = `h[n]`, alpha1, alpha2,
       and the downward 2 pi S^- gives J = `xj[n]`, K = `xk[n]`, sigma1, sigma2 (sympy, exact).
  [C7] The six layer integrals of the angular sweeps, integrated exactly by sympy, equal the code's closed forms
       (`up_ratio`, `down_ratio`, the H, J, alpha2 and sigma2 terms) at three rational (lambda, mu, dtau) points.
  [C8] C+-(t) = pi (B0 + B1 (t +- 1/(gamma1+gamma2))) solves dF+/dt = gamma1 F+ - gamma2 F- - 2 pi (1-w) B and
       dF-/dt = gamma2 F+ - gamma1 F- + 2 pi (1-w) B for the hemispheric-mean gammas (sympy).

Run: python3 longwave_check.py (numpy and sympy only; about a second). Exit status: number of failures.
"""
import sys

import numpy as np
import sympy as sp

w, g, B, A = sp.symbols("omega g B A_s", positive=True)
mu1 = sp.Rational(1, 2)


def report(label, ok, text):
    ok = bool(ok)
    print(f"[{label}] {'PASS' if ok else 'FAIL'} {text}")
    return ok


def hemispheric(wv, gv):
    """Toon et al. 1989 Table 1, hemispheric-mean row"""
    return 2 - wv * (1 + gv), wv * (1 - gv)


def check_C1_alpha_form():
    g1, g2 = hemispheric(w, g)
    lam_toon = sp.sqrt(g1 ** 2 - g2 ** 2)
    a = sp.sqrt((1 - w) / (1 - w * g))               # `alp[k]`
    lam_code = a * (1 - w * g) / mu1                 # `lam[k]`
    gam_code = (1 - a) / (1 + a)                     # `gam[k]`
    gam_toon = g2 / (g1 + lam_toon)
    # compare on a grid of exact rationals with 0 < w < 1, 0 <= g < 1 (sympy simplification of nested roots is
    # not reliable in general, so the identities are evaluated exactly, then also squared symbolically)
    ok_sym = sp.simplify(lam_code ** 2 - (g1 ** 2 - g2 ** 2)) == 0
    pts = [(sp.Rational(i, 10), sp.Rational(j, 10)) for i in range(1, 10) for j in range(0, 10)]
    ok_num = all(abs(sp.N((lam_code - lam_toon).subs({w: a_, g: b_}), 50)) < 1e-45 and
                 abs(sp.N((gam_code - gam_toon).subs({w: a_, g: b_}), 50)) < 1e-45 for a_, b_ in pts)
    return report("C1", ok_sym and ok_num, "a = sqrt((1-w)/(1-wg)): lambda = 2a(1-wg) = sqrt(gamma1^2-gamma2^2) and "
                  "Gamma = (1-a)/(1+a) = gamma2/(gamma1+lambda), 90 exact (w, g) points to 1e-45 and lambda^2 symbolically")


def check_C2_term():
    g1, g2 = hemispheric(w, g)
    ok1 = sp.simplify(mu1 / (1 - w * g) - 1 / (g1 + g2)) == 0
    ok2 = sp.simplify((1 / (g1 + g2) - mu1) - mu1 * w * g / (1 - w * g)) == 0
    return report("C2", ok1 and ok2, "term = mu1/(1-wg) = 1/(gamma1+gamma2); 1/(gamma1+gamma2) - mu1 = mu1 w g/(1-wg)")


def gauss_mu_weight(n):
    """Golub-Welsch for the weight mu on [0, 1]: shifted Jacobi (alpha, beta) = (0, 1)"""
    a, b = 0.0, 1.0
    k = np.arange(n, dtype=float)
    diag = (b * b - a * a) / ((2 * k + a + b) * (2 * k + a + b + 2))
    kk = np.arange(1, n, dtype=float)
    off = 2 / (2 * kk + a + b) * np.sqrt(kk * (kk + a) * (kk + b) * (kk + a + b) /
                                         ((2 * kk + a + b - 1) * (2 * kk + a + b + 1)))
    J = np.diag(diag) + np.diag(off, 1) + np.diag(off, -1)
    x, V = np.linalg.eigh(J)
    mu0 = 2.0 ** (a + b + 1) / (a + b + 1)           # int_{-1}^{1} (1+x) dx = 2
    wx = mu0 * V[0, :] ** 2
    return (1 + x) / 2, wx / 4                        # map to [0, 1]: weight mu dmu = (1+x)/2 dx/2


UARR = np.array([0.0985350858, 0.3045357266, 0.5620251898, 0.8019865821, 0.9601901429])
WUARR = np.array([0.0157479145, 0.0739088701, 0.1463869871, 0.1671746381, 0.0967815902])


def check_C3_quadrature():
    nodes, weights = gauss_mu_weight(5)
    dn = np.max(np.abs(nodes - UARR))
    dw = np.max(np.abs(weights - WUARR))
    exact = max(abs(np.sum(WUARR * UARR ** k) - 1 / (k + 2)) for k in range(10))
    ok = dn < 1e-10 and dw < 1e-10 and abs(WUARR.sum() - 0.5) < 1e-10 and exact < 1e-10   # 10 decimals stored
    return report("C3", ok, f"max|node - uarr| = {dn:.1e}, max|weight - wuarr| = {dw:.1e}, sum w = {WUARR.sum():.10f}, "
                  f"max_k<=9 |sum w mu^k - 1/(k+2)| = {exact:.1e}")


def rhs_two_layers(Btop, bsurf, Asfc, Cp, Cm, Cpm1, Cmm1, E1, E3, gam):
    """`Df` of toon_mckay89_longwave for nlay = 2, line for line"""
    D0 = Btop - Cmm1[0]
    D1 = (gam[1] - 1) * (Cpm1[1] - Cp[0]) + (1 - gam[1]) * (Cm[0] - Cmm1[1])
    D2 = E3[0] * (Cpm1[1] - Cp[0]) + E1[0] * (Cm[0] - Cmm1[1])
    D3 = bsurf - Cp[1] + Asfc * Cm[1]
    return [D0, D1, D2, D3]


def isothermal_rhs(hard):
    term = sp.symbols("t0 t1", positive=True)
    dt = sp.symbols("d0 d1", positive=True)
    gam = sp.symbols("G0 G1", positive=True)
    E1 = sp.symbols("E10 E11", positive=True)
    E3 = sp.symbols("E30 E31", positive=True)
    B0 = [B, B]
    B1 = [0, 0]
    Cpm1 = [B0[k] + B1[k] * term[k] for k in range(2)]
    Cmm1 = [B0[k] - B1[k] * term[k] for k in range(2)]
    Cp = [B0[k] + B1[k] * dt[k] + B1[k] * term[k] for k in range(2)]
    Cm = [B0[k] + B1[k] * dt[k] - B1[k] * term[k] for k in range(2)]
    bsurf = (1 - A) * B if hard else B + B1[1] * mu1
    return [sp.simplify(d) for d in rhs_two_layers(B, bsurf, A, Cp, Cm, Cpm1, Cmm1, E1, E3, gam)]


def check_C4_isothermal_hard():
    rhs = isothermal_rhs(True)
    return report("C4", all(r == 0 for r in rhs), f"hard surface: Df = {rhs} (all zero for any A_s, gamma, E)")


def check_C5_isothermal_nonhard():
    rhs = isothermal_rhs(False)
    ok = rhs[:3] == [0, 0, 0] and sp.simplify(rhs[3] - A * B) == 0
    return report("C5", ok, f"non-hard surface: Df = {rhs}; bottom entry A_s B is nonzero for A_s > 0")


def check_C6_source_coefficients():
    k1, k2, t, B0, B1, a = sp.symbols("k1 k2 t B0 B1 a", positive=True)
    lam = sp.symbols("lambda", positive=True)
    # parametrise w, g by the code's auxiliary a and w g: (1-w) = a^2 (1-w g)
    wg = sp.symbols("wg", positive=True)
    wv = 1 - a ** 2 * (1 - wg)
    gv = wg / wv
    Gam = (1 - a) / (1 + a)
    tstar = mu1 / (1 - wg)                         # 1/(gamma1 + gamma2) = `term`
    Fp = sp.pi * (k1 * sp.exp(lam * t) + Gam * k2 * sp.exp(-lam * t) + B0 + B1 * (t + tstar))
    Fm = sp.pi * (Gam * k1 * sp.exp(lam * t) + k2 * sp.exp(-lam * t) + B0 + B1 * (t - tstar))
    Splus = wv * ((1 + gv) * Fp + (1 - gv) * Fm) + 2 * sp.pi * (1 - wv) * (B0 + B1 * t)
    Sminus = wv * ((1 + gv) * Fm + (1 - gv) * Fp) + 2 * sp.pi * (1 - wv) * (B0 + B1 * t)
    tv = mu1 * wg / (1 - wg)                       # `term_val`
    G = 2 * sp.pi * wv * k1 * (1 + gv * a) / (1 + a)
    H = 2 * sp.pi * wv * k2 * (1 - gv * a) / (1 + a)
    J = 2 * sp.pi * wv * k1 * (1 - gv * a) / (1 + a)
    K = 2 * sp.pi * wv * k2 * (1 + gv * a) / (1 + a)
    al1, al2 = 2 * sp.pi * (B0 + B1 * tv), 2 * sp.pi * B1
    si1, si2 = 2 * sp.pi * (B0 - B1 * tv), 2 * sp.pi * B1
    r1 = sp.simplify(Splus - (G * sp.exp(lam * t) + H * sp.exp(-lam * t) + al1 + al2 * t))
    r2 = sp.simplify(Sminus - (J * sp.exp(lam * t) + K * sp.exp(-lam * t) + si1 + si2 * t))
    return report("C6", r1 == 0 and r2 == 0, "2 pi S+ = G e^{lam t} + H e^{-lam t} + alpha1 + alpha2 t and "
                  "2 pi S- = J e^{lam t} + K e^{-lam t} + sigma1 + sigma2 t with the code's coefficients")


def check_C7_sweep_integrals():
    t, d, lam, mu = sp.symbols("t Delta lambda mu", positive=True)
    up_ratio = (sp.exp(lam * d) * sp.exp(-d / mu) - 1) / (lam * mu - 1)       # G term, upward
    h_term = (1 - sp.exp(-lam * d) * sp.exp(-d / mu)) / (lam * mu + 1)          # H term, upward
    a2_term = mu - (d + mu) * sp.exp(-d / mu)                                   # alpha2 term, upward
    j_term = (sp.exp(lam * d) - sp.exp(-d / mu)) / (lam * mu + 1)               # J term, downward
    down_ratio = (sp.exp(-d / mu) - sp.exp(-lam * d)) / (lam * mu - 1)          # K term, downward
    s2_term = mu * sp.exp(-d / mu) + d - mu                                     # sigma2 term, downward
    up = lambda f: sp.integrate(f * sp.exp(-t / mu), (t, 0, d)) / mu
    dn = lambda f: sp.integrate(f * sp.exp(-(d - t) / mu), (t, 0, d)) / mu
    pairs = [(up(sp.exp(lam * t)), up_ratio), (up(sp.exp(-lam * t)), h_term), (up(t), a2_term),
             (dn(sp.exp(lam * t)), j_term), (dn(sp.exp(-lam * t)), down_ratio), (dn(t), s2_term)]
    pts = [{lam: sp.Rational(7, 5), mu: sp.Rational(3, 10), d: sp.Rational(2, 3)},
           {lam: sp.Rational(1, 3), mu: sp.Rational(9, 10), d: sp.Rational(5, 2)},
           {lam: sp.Rational(5, 2), mu: sp.Rational(1, 10), d: sp.Rational(1, 7)}]   # all away from lambda mu = 1
    worst = max(abs(sp.N((a - b).subs(p), 50)) for a, b in pairs for p in pts)
    ok = worst < 1e-40
    return report("C7", ok, f"the six layer integrals of the sweeps (G, H, alpha2 up; J, K, sigma2 down) minus the code's closed "
                  f"forms, integrated exactly and evaluated at 3 rational points to 50 digits: max {float(worst):.0e}")


def check_C8_particular():
    t, B0, B1 = sp.symbols("t B0 B1", positive=True)
    g1, g2 = hemispheric(w, g)
    ts = 1 / (g1 + g2)
    Cp = sp.pi * (B0 + B1 * (t + ts))
    Cm = sp.pi * (B0 + B1 * (t - ts))
    S = 2 * sp.pi * (1 - w) * (B0 + B1 * t)
    r1 = sp.simplify(sp.diff(Cp, t) - (g1 * Cp - g2 * Cm - S))
    r2 = sp.simplify(sp.diff(Cm, t) - (g2 * Cp - g1 * Cm + S))
    return report("C8", r1 == 0 and r2 == 0, "C+- = pi (B0 + B1 (t +- 1/(gamma1+gamma2))) solves the thermal two-stream "
                  "equations exactly")


def main():
    oks = [check_C1_alpha_form(), check_C2_term(), check_C3_quadrature(), check_C4_isothermal_hard(),
           check_C5_isothermal_nonhard(), check_C6_source_coefficients(), check_C7_sweep_integrals(), check_C8_particular()]
    print(f"RESULT: {sum(oks)}/{len(oks)} pass")
    return len(oks) - sum(oks)


if __name__ == "__main__":
    sys.exit(main())
