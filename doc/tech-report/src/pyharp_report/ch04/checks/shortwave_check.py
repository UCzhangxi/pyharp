#!/usr/bin/env python3
"""Check of the shortwave two-stream derivation of chapter 4 (scheme file `_shortwave.qmd`).

Mirrors the formulas of `toon_mckay89_shortwave` in src/rtsolver/toon_mckay89_shortwave_impl.h of pyharp at the
pin of code_pin.yml (Toon et al. 1989 Table 1 quadrature row, eqs. 21-24; delta-Eddington of Joseph et al. 1976).

  [C1] lambda^2 = gamma1^2 - gamma2^2 is the eigenvalue of the homogeneous two-stream system, and
       Gamma = (gamma1 - lambda)/gamma2 is the ratio F+/F- of its decaying mode (sympy, exact).
  [C2] C+ and C- of the code (Ap, Am times e^{-tau/mu0}) solve the forced system exactly (sympy).
  [C3] delta-Eddington: g' = (g - f)/(1 - f) = g/(1 + g) for f = g^2, and the absorption optical depth
       (1 - w') tau' = (1 - w) tau is unchanged by the scaling (sympy).
  [C4] w = 1: gamma1 = gamma2, so lambda = 0, Gamma = 1 and every interface row coefficient 1 - Gamma^2 vanishes
       (sympy); the tridiagonal system is singular there.
  [C5] the unscaled exponential e^{lambda dtau}, capped at e^{35}: round-off e^{x} eps reaches 1 at
       x = ln(1/eps) = 36.04 and 1e-9 at x = 15.3 (numpy, double).
  [C7] the step from the second row of the particular-solution system to the second displayed line of the chapter's
       elimination: that line is the second row multiplied by ROW2_MULTIPLIER = gamma2 (sympy, exact); with the
       multiplier gamma1 - 1/mu0 the identity fails, so a wrong multiplier in the prose turns this check red.
  [C6] the resonance guard: |lambda mu0 - 1| < sqrt(eps) moves mu0 by at most sqrt(eps) = 1.49e-8 relative.

Run: python3 shortwave_check.py (numpy and sympy only; well under a second). Exit status: number of failures.
"""
import sys

import numpy as np
import sympy as sp

w, g, mu0, tau, F0 = sp.symbols("omega g mu_0 tau F_0", positive=True)
s3 = sp.sqrt(3)


def gammas(wp, gp):
    """Table 1 quadrature row, as `g1..g4` in toon_mckay89_shortwave"""
    g1 = s3 / 2 * (2 - wp * (1 + gp))
    g2 = s3 / 2 * wp * (1 - gp)
    g3 = (1 - s3 * gp * mu0) / 2
    return g1, g2, g3, 1 - g3


def report(label, ok, text):
    ok = bool(ok)
    print(f"[{label}] {'PASS' if ok else 'FAIL'} {text}")
    return ok


def check_C1_eigen():
    g1, g2, _, _ = gammas(w, g)
    lam = sp.sqrt(g1 ** 2 - g2 ** 2)
    A = sp.Matrix([[g1, -g2], [g2, -g1]])            # d/dtau (F+, F-) = A (F+, F-), Toon eqs. 11-12
    ev = sorted(A.eigenvals().keys(), key=sp.default_sort_key)
    ok1 = all(sp.simplify(e ** 2 - lam ** 2) == 0 for e in ev)
    Gam = (g1 - lam) / g2
    vec = sp.Matrix([Gam, 1])                         # decaying mode e^{-lambda tau}: (F+, F-) = (Gamma, 1)
    ok2 = sp.simplify(A * vec + lam * vec) == sp.zeros(2, 1)
    return report("C1", ok1 and ok2, "eigenvalues +-lambda with lambda^2 = gamma1^2 - gamma2^2; decaying mode "
                  "has F+/F- = Gamma = (gamma1 - lambda)/gamma2")


def check_C2_particular():
    g1, g2, g3, g4 = gammas(w, g)
    lam2 = g1 ** 2 - g2 ** 2
    den = lam2 - 1 / mu0 ** 2
    Ap = F0 * w * (g3 * (g1 - 1 / mu0) + g2 * g4) / den      # `Ap[i]` in the code
    Am = F0 * w * (g4 * (g1 + 1 / mu0) + g2 * g3) / den      # `Am[i]`
    e = sp.exp(-tau / mu0)
    Cp, Cm = Ap * e, Am * e
    r1 = sp.diff(Cp, tau) - (g1 * Cp - g2 * Cm - g3 * w * F0 * e)
    r2 = sp.diff(Cm, tau) - (g2 * Cp - g1 * Cm + g4 * w * F0 * e)
    ok = sp.simplify(r1) == 0 and sp.simplify(r2) == 0
    return report("C2", ok, "C+ = Ap e^{-tau/mu0}, C- = Am e^{-tau/mu0} satisfy dF+/dtau = g1 F+ - g2 F- - g3 w F0 "
                  "e^{-tau/mu0} and dF-/dtau = g2 F+ - g1 F- + g4 w F0 e^{-tau/mu0} exactly")


def check_C3_delta():
    f = g ** 2
    wp = (1 - f) * w / (1 - w * f)
    tp = (1 - w * f) * tau
    ok1 = sp.simplify((g - f) / (1 - f) - g / (1 + g)) == 0
    ok2 = sp.simplify((1 - wp) * tp - (1 - w) * tau) == 0
    ok3 = sp.simplify(wp * tp - (1 - f) * w * tau) == 0
    return report("C3", ok1 and ok2 and ok3, "f = g^2: g' = (g-f)/(1-f) = g/(1+g); (1-w')tau' = (1-w)tau; "
                  "w' tau' = (1-f) w tau")


def check_C4_conservative():
    gp = sp.symbols("gp", positive=True)
    g1, g2, _, _ = gammas(sp.Integer(1), gp)
    lam = sp.sqrt(sp.simplify(g1 ** 2 - g2 ** 2))
    Gam = sp.simplify((g1 - lam) / g2)
    ok = sp.simplify(g1 - g2) == 0 and lam == 0 and Gam == 1 and sp.simplify(1 - Gam ** 2) == 0
    return report("C4", ok, "w' = 1: gamma1 = gamma2, lambda = 0, Gamma = 1, interface coefficient 1 - Gamma^2 = 0")


def check_C5_clamp():
    eps = np.finfo(np.float64).eps
    x_one = np.log(1 / eps)
    x_1e9 = np.log(1e-9 / eps)
    ok = abs(x_one - 36.04) < 0.01 and abs(x_1e9 - 15.33) < 0.01 and np.exp(-35.0) < 7e-16
    return report("C5", ok, f"eps = {eps:.3e}: e^x eps = 1 at x = {x_one:.2f}, = 1e-9 at x = {x_1e9:.2f}; "
                  f"e^-35 = {np.exp(-35.0):.2e}")


def check_C6_resonance():
    eps = np.finfo(np.float64).eps
    tol = np.sqrt(eps)
    lam = 1.2247448713915890
    mu = 1 / lam                                     # exact resonance
    res = lam * mu - 1
    if abs(res) < tol:                               # the code's guard, line for line
        mu_new = (1 + (-tol if res < 0 else tol)) / lam
    rel = abs(mu_new - mu) / mu
    ok = abs(rel - tol) < 1e-15 and abs(lam * mu_new - 1) >= tol * (1 - 1e-12)
    return report("C6", ok, f"guard shift |dmu0|/mu0 = {rel:.3e} = sqrt(eps) = {tol:.3e}")


ROW2_MULTIPLIER = "gamma2"   # the multiplier the chapter's prose names for the second line of the elimination


def check_C7_elimination_multiplier():
    g1, g2, g3, g4 = gammas(w, g)
    cp, cm = sp.symbols("c_p c_m")
    # second row of the particular-solution system, -c-/mu0 = g2 c+ - g1 c- + g4 w F0, written as lhs - rhs = 0
    row2 = (g1 - 1 / mu0) * cm - (g2 * cp + g4 * w * F0)
    # the chapter's second displayed line: (g1 - 1/mu0) g2 c- = g2^2 c+ + g4 g2 w F0
    line2 = (g1 - 1 / mu0) * g2 * cm - (g2 ** 2 * cp + g4 * g2 * w * F0)
    mult = {"gamma2": g2, "gamma1 - 1/mu0": g1 - 1 / mu0}[ROW2_MULTIPLIER]
    ok = sp.simplify(line2 - mult * row2) == 0
    return report("C7", ok, f"second displayed line of the elimination = second row x {ROW2_MULTIPLIER}")


def main():
    oks = [check_C1_eigen(), check_C2_particular(), check_C3_delta(), check_C4_conservative(), check_C5_clamp(),
           check_C6_resonance(), check_C7_elimination_multiplier()]
    print(f"RESULT: {sum(oks)}/{len(oks)} pass")
    return len(oks) - sum(oks)


if __name__ == "__main__":
    sys.exit(main())
