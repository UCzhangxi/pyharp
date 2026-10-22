"""ch02 check: delta-M (Wiscombe 1977) at the two-stream truncation reduces to delta-Eddington (f = g^2).

Wiscombe (1977, J. Atmos. Sci. 34, 1408, doi:10.1175/1520-0469(1977)034<1408:tdmrya>2.0.co;2): eq. (12) Henyey-Greenstein
moments chi_n = g^n; eq. (13) the truncated phase function, "M = 1 leads to the delta-Eddington approximation";
eq. (14) chi*_m = (chi_m - f)/(1 - f); eq. (15) f = chi_2M; eq. (17) the difference to the full phase function;
eq. (20) dtau' = (1 - w f) dtau, w' = (1 - f) w / (1 - w f). Joseph, Wiscombe & Weinman (1976,
doi:10.1175/1520-0469(1976)033<2452:tdeafr>2.0.co;2), as quoted by Meador & Weaver (1980) eq. (59), for C3 and C6.

Pure algebra and quadrature: no pyharp code is mirrored here (the code side is check_ch02_toon_coefficients.py
C1-C3, C25). Needs sympy (mpmath ships with it). Run: python3 check_ch02_delta_scaling.py (exits with the failures).
"""

import sys

import mpmath as mp
import sympy as sp

g, w, tau, x, f, mu, mup = sp.symbols("g omega tau x f mu muprime", real=True)
M = 1
chi = {n: g**n for n in range(6)}                                     # eq. (12)
fM = chi[2 * M]                                                       # eq. (15)
chis = {m: sp.simplify((chi[m] - fM) / (1 - fM)) for m in range(2 * M)}  # eq. (14)
ts, ws, gs = (1 - w * g**2) * tau, (1 - g**2) * w / (1 - w * g**2), g / (1 + g)


def report(n, ok, label, detail):
    print(f"[C{n}] {'PASS' if ok else 'FAIL'} {label}: {detail}")
    return bool(ok)


def check_C1():
    ok = fM == g**2 and chis[0] == 1 and sp.simplify(chis[1] - g / (1 + g)) == 0
    return report(1, ok, "M = 1 truncation fraction and moments", f"f = {fM}, chi*_0 = {chis[0]}, chi*_1 = {chis[1]}")


def check_C2():
    mom = [sp.simplify(fM + ((1 - fM) * chis[n] if n < 2 * M else 0)) for n in range(6)]
    eq = [sp.simplify(mom[n] - chi[n]) == 0 for n in range(6)]
    return report(2, eq[:3] == [True] * 3 and not any(eq[3:]), "moments of P* vs HG (eq. 17)",
                  f"P*: {mom}; equal to g^n for n = 0, 1, 2, different from n = 3 = 2M + 1")


def check_C3():
    smooth = (1 - fM) * sum((2 * n + 1) * chis[n] * sp.legendre(n, mu) * sp.legendre(n, mup) for n in range(2 * M))
    joseph = (1 - g**2) * (1 + 3 * g * mu * mup / (1 + g))
    return report(3, sp.simplify(smooth - joseph) == 0, "eqs. 18-19 at M = 1 = Joseph's phase function (MW eq. 59)",
                  f"smooth parts differ by {sp.simplify(smooth - joseph)}; delta weight 2f = {2 * fM}")


def check_C4():
    I, Jc = sp.symbols("I Jcal")  # mu dI/dtau = -I + w (f I + (1 - f) Jcal), divided by (1 - w f)
    d = sp.simplify((-I + w * (f * I + (1 - f) * Jc)) / (1 - w * f) - (-I + (1 - f) * w / (1 - w * f) * Jc))
    return report(4, d == 0, "the transfer equation keeps its form under eq. 20", f"residual {d}")


def check_C5():
    i1 = sp.simplify((1 - ws) * ts - (1 - w) * tau)
    i2 = sp.simplify(ws * ts * (1 - gs) - w * tau * (1 - g))
    return report(5, i1 == 0 and i2 == 0 and sp.simplify(ws.subs(w, 1)) == 1, "invariants at f = g^2",
                  f"(1-w')tau' - (1-w)tau = {i1}; w'tau'(1-g') - w tau(1-g) = {i2}; w'(w = 1) = 1")


def check_C6():
    """Eddington ansatz (MW eq. 30) with Joseph's p in unscaled tau = (1 - w g^2) x Eddington row at (w', g')."""
    nu, m = sp.symbols("nu m", positive=True)
    Ip, Im, mu0 = sp.symbols("Ip Im mu0")
    Iu = ((2 + 3 * nu) * Ip + (2 - 3 * nu) * Im) / 2
    Id = ((2 - 3 * nu) * Ip + (2 + 3 * nu) * Im) / 2
    pl = lambda a, b: w * (1 - g**2) * (1 + 3 * gs * a * b)
    scat = sp.Rational(1, 2) * (sp.integrate(sp.integrate(pl(m, nu) * Iu, (nu, 0, 1)), (m, 0, 1))
                                + sp.integrate(sp.integrate(pl(m, -nu) * Id, (nu, 0, 1)), (m, 0, 1)))
    rhs = sp.expand(sp.integrate(Iu, (nu, 0, 1)) - scat - w * g**2 * sp.integrate(Iu.subs(nu, m), (m, 0, 1)))
    e1, e2 = (7 - ws * (4 + 3 * gs)) / 4, -(1 - ws * (4 - 3 * gs)) / 4
    e3 = (2 - 3 * gs * mu0) / 4
    b0 = sp.integrate(pl(mu0, -m), (m, 0, 1)) / (2 * w)  # the delta term does not reach mu' = -mu0
    ok = (sp.simplify(rhs.coeff(Ip) - (1 - w * g**2) * e1) == 0 and sp.simplify(-rhs.coeff(Im) - (1 - w * g**2) * e2) == 0
          and sp.simplify(w * b0 - (1 - w * g**2) * ws * e3) == 0)
    return report(6, ok, "delta-Eddington = Eddington row at (w', g') per unit tau'", "g1, g2 and w beta0 exact")


def check_C7():
    chiR = [sp.integrate(sp.Rational(3, 4) * (1 + x**2) * sp.legendre(n, x), (x, -1, 1)) / 2 for n in range(3)]
    return report(7, chiR == [1, 0, sp.Rational(1, 10)], "Rayleigh: delta-M f = chi_2 differs from g^2",
                  f"chi_0..2 = {chiR}: f = 1/10 for delta-M (M = 1), f = g^2 = 0 for delta-Eddington")


def check_C8():
    mp.mp.dps = 35
    dev = []
    for gv in (mp.mpf("0.3"), mp.mpf("0.75"), mp.mpf("0.85")):
        hg = lambda c: (1 - gv**2) / (1 + gv**2 - 2 * gv * c)**mp.mpf(1.5)
        dev += [abs(mp.quad(lambda c: hg(c) * mp.legendre(n, c), [-1, 0, 1]) / 2 - gv**n) for n in (1, 2, 3)]
    return report(8, max(dev) < mp.mpf("1e-28"), "HG moments chi_n = g^n by 35-digit quadrature",
                  "g = 0.3, 0.75, 0.85; n = 1, 2, 3; max deviation below 1e-28")


def main():
    res = [c() for c in (check_C1, check_C2, check_C3, check_C4, check_C5, check_C6, check_C7, check_C8)]
    nfail = res.count(False)
    print(f"check_ch02_delta_scaling: {len(res) - nfail} of {len(res)} claims pass")
    return nfail


if __name__ == "__main__":
    sys.exit(main())
