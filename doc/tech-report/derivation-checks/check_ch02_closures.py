"""ch02 check: the two-stream closure family (Meador & Weaver 1980) reproduces each named closure exactly.

What is checked. Meador & Weaver (1980, J. Atmos. Sci. 37, 630, doi:10.1175/1520-0469(1980)037<0630:tsatrt>2.0.co;2),
eqs. (10)-(11), are the exact hemispheric moments of the azimuth-integrated transfer equation. A closure is an
ansatz for the intensity I(tau, +-mu) in terms of the hemispheric fluxes I+, I- plus a rule for the phase-function
integrals. Matching to MW eqs. (12)-(13),
    dI+/dtau =  g1 I+ - g2 I- - pi F w g3 exp(-tau/mu0),
    dI-/dtau =  g2 I+ - g1 I- + pi F w g4 exp(-tau/mu0),
defines gamma1..gamma4. Each closure below is entered only as its ansatz; sympy derives the gammas and compares
them with the coefficients as printed in MW Table 1 (p. 633) and Toon et al. (1989, JGR 94, 16287,
doi:10.1029/jd094id13p16287) Table 1 (p. 16,289). The printed rows are transcribed from the page images.
C17-C20 map the discrete-ordinate equations of Stamnes et al. (1988, Appl. Opt. 27, 2502, doi:10.1364/ao.27.002502)
at N = 1 (NSTR = 2) onto the same notation. C21-C22 are the energy constraints MW eqs. (21) and (23).

Pure algebra: no pyharp code is mirrored, so no code sha applies. Needs sympy (mpmath ships with it).
Run: python3 check_ch02_closures.py   (any directory; exits with the number of failed claims)
"""

import sys

import sympy as sp

w, g, mu0, mu, nu = sp.symbols("omega g mu0 mu nu", positive=True)
b0, b1, bh = sp.symbols("beta0 beta1 beta", positive=True)
Ip, Im = sp.symbols("Iplus Iminus")
r3 = sp.sqrt(3)
Dh = 1 - g**2 * (1 - mu0)


def p_lin(x, y):
    """MW eq. (3) truncated at l = 1 (the phase function carries w, MW eq. (2))."""
    return w * (1 + 3 * g * x * y)


def p_hemi(same):
    """Toon Table 1 footnote: 1 + g in the forward hemisphere, 1 - g in the backward one (times w)."""
    return w * (1 + g) if same else w * (1 - g)


def derive(c):
    """gamma1..gamma4 from MW eqs. (10)-(11) for the closure description c (see CLOSURES)."""
    eqs = {}
    for s in (1, -1):  # +1: upward eq. (10); -1: downward eq. (11)
        stream, scat = 0, 0
        if "cont" in c:  # continuous ansatz I(tau, s nu) = a(nu) I+ + b(nu) I-
            a, b = c["cont"][s]
            stream += sp.integrate(a.subs(nu, mu), (mu, 0, 1)) * Ip + sp.integrate(b.subs(nu, mu), (mu, 0, 1)) * Im
            for sn in (1, -1):
                an, bn = c["cont"][sn]
                ker = p_hemi(s * sn > 0) if c["cont_p"] == "hemi" else p_lin(s * mu, sn * nu)
                for coef, I in ((an, Ip), (bn, Im)):
                    scat += sp.Rational(1, 2) * sp.integrate(sp.integrate(ker * coef, (nu, 0, 1)), (mu, 0, 1)) * I
        if "hconst" in c:  # MW eqs. (45)-(47): I(tau, +-mu) = 2 I+-, true p kept as beta
            same, other = (Ip, Im) if s == 1 else (Im, Ip)
            stream += 2 * same
            scat += 2 * w * (1 - bh) * same + 2 * w * bh * other
        for node, cu, cd in c.get("delta", []):  # I(tau, s nu) += coeff_s delta(nu - node)
            stream += cu if s == 1 else cd
            for sn, cp in ((1, cu), (-1, cd)):
                same = s * sn > 0
                if c["delta_p"] == "full":  # 1/2 int_0^1 p(s mu, sn node) dmu = w(1-beta) or w beta
                    bs = c["beta_of"][node]
                    scat += cp * (w * (1 - bs) if same else w * bs)
                else:  # 'quad': the outer integral by the same one-point rule (Liou, MW p. 635)
                    scat += cp * sp.Rational(1, 2) * p_lin(s * c["qnode"], sn * node)
        eqs[s] = sp.expand(s * stream - s * scat)
    out = dict(g1=sp.simplify(eqs[1].coeff(Ip)), g2=sp.simplify(-eqs[1].coeff(Im)))
    out["sym"] = sp.simplify(out["g1"] + eqs[-1].coeff(Im)) == 0 and sp.simplify(out["g2"] - eqs[-1].coeff(Ip)) == 0
    beam = c["beam"]  # beta0 = 1/(2w) int_0^1 p(mu0, -mu') dmu' (MW eq. 9)
    if beam == "lin":
        out["g3"] = sp.integrate(p_lin(mu0, -mu), (mu, 0, 1)) / (2 * w)
        out["g4"] = sp.integrate(p_lin(mu0, mu), (mu, 0, 1)) / (2 * w)
    elif beam == "full":
        out["g3"], out["g4"] = b0, 1 - b0
    elif beam == "quad":
        out["g3"], out["g4"] = p_lin(c["qnode"], -mu0) / (2 * w), p_lin(c["qnode"], mu0) / (2 * w)  # MW eqs. 41, 42
    norm = 0  # MW eq. (8): int_0^1 mu I(tau, mu) dmu = I+
    if "cont" in c:
        a, b = c["cont"][1]
        norm += sp.integrate(mu * a.subs(nu, mu), (mu, 0, 1)) * Ip + sp.integrate(mu * b.subs(nu, mu), (mu, 0, 1)) * Im
    if "hconst" in c:
        norm += Ip
    for node, cu, _ in c.get("delta", []):
        norm += node * cu
    out["eq8"] = sp.simplify(norm - Ip) == 0
    return out


EDD = {1: ((2 + 3 * nu) / 2, (2 - 3 * nu) / 2), -1: ((2 - 3 * nu) / 2, (2 + 3 * nu) / 2)}  # MW eq. (30)
CLOSURES = {
    "Eddington": dict(cont=EDD, cont_p="lin", beam="lin"),
    "modified Eddington": dict(cont=EDD, cont_p="lin", beam="full"),
    "quadrature": dict(delta=[(1 / r3, r3 * Ip, r3 * Im)], qnode=1 / r3, delta_p="quad", beam="quad"),
    "modified quadrature": dict(delta=[(1 / r3, r3 * Ip, r3 * Im)], delta_p="full", beta_of={1 / r3: b1}, beam="full"),
    "hemispheric constant": dict(hconst=True, beam="full"),
    "delta function": dict(delta=[(mu0, Ip / mu0, Im / mu0)], delta_p="full", beta_of={mu0: b0}, beam="full"),
    "hybrid": dict(cont={s: tuple((1 - g**2) * e / Dh for e in EDD[s]) for s in (1, -1)}, cont_p="lin",
                   delta=[(mu0, g**2 * Ip / Dh, g**2 * Im / Dh)], delta_p="full", beta_of={mu0: b0}, beam="full"),
    "hemispheric mean": dict(cont={1: (sp.Integer(2), sp.Integer(0)), -1: (sp.Integer(0), sp.Integer(2))},
                             cont_p="hemi", beam="none"),
}
E_ROW = dict(g1=(7 - w * (4 + 3 * g)) / 4, g2=-(1 - w * (4 - 3 * g)) / 4, g3=(2 - 3 * g * mu0) / 4)
Q_ROW = dict(g1=r3 / 2 * (2 - w * (1 + g)), g2=r3 * w / 2 * (1 - g), g3=(1 - r3 * g * mu0) / 2)
# (closure, source, printed coefficients); MW Table 1 p. 633, Toon Table 1 p. 16,289
PRINTED = [
    ("Eddington", "MW80 Table 1", E_ROW),
    ("Eddington", "Toon89 Table 1", E_ROW),
    ("modified Eddington", "MW80 Table 1", dict(g1=E_ROW["g1"], g2=E_ROW["g2"], g3=b0)),
    ("quadrature", "MW80 Table 1 + eq. 42", dict(Q_ROW, g4=(1 + r3 * g * mu0) / 2)),
    ("quadrature", "Toon89 Table 1", Q_ROW),
    ("modified quadrature", "MW80 Table 1", dict(g1=r3 * (1 - w * (1 - b1)), g2=r3 * w * b1, g3=b0)),
    ("hemispheric constant", "MW80 Table 1", dict(g1=2 * (1 - w * (1 - bh)), g2=2 * w * bh, g3=b0)),
    ("delta function", "MW80 Table 1", dict(g1=(1 - w * (1 - b0)) / mu0, g2=w * b0 / mu0, g3=b0)),
    ("hybrid", "MW80 Table 1", dict(g1=(7 - 3 * g**2 - w * (4 + 3 * g) + w * g**2 * (4 * b0 + 3 * g)) / (4 * Dh),
                                    g2=-(1 - g**2 - w * (4 - 3 * g) - w * g**2 * (4 * b0 + 3 * g - 4)) / (4 * Dh),
                                    g3=b0)),
    ("hemispheric mean", "Toon89 Table 1", dict(g1=2 - w * (1 + g), g2=w * (1 - g))),
]
DERIVED = {}


def report(n, ok, label, detail):
    print(f"[C{n}] {'PASS' if ok else 'FAIL'} {label}: {detail}")
    return bool(ok)


def check_rows():
    """C1-C10: one claim per printed row (derived minus printed simplifies to 0, including the derived g4 against
    1 - printed g3 for every row that prints g3; eqs. 12-13 symmetric; eq. 8)."""
    res = []
    for n, (name, src, row) in enumerate(PRINTED, start=1):
        d = DERIVED.setdefault(name, derive(CLOSURES[name]))
        diff = {k: sp.simplify(d[k] - v) for k, v in row.items()}
        if "g3" in row:  # the table prints g3 only; g4 = 1 - g3 must also hold for the derived g4
            diff["g4=1-g3"] = sp.simplify(d["g4"] - (1 - row["g3"]))
        ok = all(v == 0 for v in diff.values()) and d["sym"] and d["eq8"]
        res.append(report(n, ok, f"{name} vs {src}", f"derived minus printed {diff}"))
    return res


def check_C11_hm_is_hconst():
    """Toon HM = MW hemispheric constant with beta = (1-g)/2, the eq. (47) value for p = 1 +- g."""
    bt = sp.Rational(1, 2) * p_hemi(False) / w
    ok = sp.simplify(2 * (1 - w * (1 - bt)) - (2 - w * (1 + g))) == 0 and sp.simplify(2 * w * bt - w * (1 - g)) == 0
    return report(11, ok, "hemispheric mean = hemispheric constant at beta=(1-g)/2", f"beta = {sp.simplify(bt)}")


def gq(m, bb):  # MW eqs. (37)-(38)
    return (1 - w * (1 - bb)) / m, w * bb / m


def check_C12_quadrature_general():
    """Quadrature g1, g2 = eqs. (37)-(38), mu1 = 3^-1/2, beta1 by the one-point rule (= Sagan-Pollack eq. 43)."""
    b1q = sp.simplify(p_lin(1 / r3, -1 / r3) / (2 * w))
    a, b = gq(1 / r3, b1q)
    ok = b1q == (1 - g) / 2 and sp.simplify(a - Q_ROW["g1"]) == 0 and sp.simplify(b - Q_ROW["g2"]) == 0
    return report(12, ok, "quadrature = MW eqs. 37-38 at mu1=3^-1/2", f"beta1 = {b1q}")


def check_C13_delta_function_general():
    a, b = gq(mu0, b0)
    ok = sp.simplify(a - PRINTED[7][2]["g1"]) == 0 and sp.simplify(b - PRINTED[7][2]["g2"]) == 0
    return report(13, ok, "delta function = MW eqs. 37-39 at mu1=mu0, beta1=beta0", "exact")


def check_C14_hybrid_limits():
    h = PRINTED[8][2]
    ok0 = all(sp.simplify(h[k].subs(g, 0) - E_ROW[k].subs(g, 0)) == 0 for k in ("g1", "g2"))
    ok1 = all(sp.simplify(h[k].subs(g, 1) - PRINTED[7][2][k]) == 0 for k in ("g1", "g2"))
    return report(14, ok0 and ok1, "hybrid -> Eddington at g=0, -> delta function at g=1", f"{ok0}, {ok1}")


def check_C15_eddington_g3():
    b0l = sp.integrate(p_lin(mu0, -mu), (mu, 0, 1)) / (2 * w)
    return report(15, sp.simplify(b0l - E_ROW["g3"]) == 0, "Eddington g3 = beta0 of the l<=1 phase function",
                  f"beta0 = {sp.simplify(b0l)}")


def check_C16_negative_control():
    """The comparison detects a wrong row and a one-character typo (g -> 2g)."""
    d = DERIVED["Eddington"]
    ok = sp.simplify(d["g1"] - Q_ROW["g1"]) != 0 and sp.simplify(d["g2"] + (1 - w * (4 - 6 * g)) / 4) != 0
    return report(16, ok, "negative control", "Eddington != quadrature row; typo detected")


# ---- Stamnes et al. 1988 at N = 1 (NSTR = 2) ----
MU1, W1 = sp.Rational(1, 2), sp.Integer(1)  # double-Gauss, one node per hemisphere (S88 p. 2504, Sec. C)
D = lambda a, b: w / 2 * sum((2 * l + 1) * g**l * sp.legendre(l, a) * sp.legendre(l, b) for l in range(2))  # eq. 6b
ALPHA = (D(MU1, MU1) * W1 - 1) / MU1   # alpha = M^-1 (D+ W - I), p. 2504
BETA = D(MU1, -MU1) * W1 / MU1         # beta  = M^-1 D- W


def check_C17_double_gauss_node():
    x = sp.Symbol("x")
    node = sp.solve(sp.legendre(1, 2 * x - 1), x)[0]
    return report(17, node == MU1, "double-Gauss N=1 node and weight", f"mu_1 = {node}, w_1 = {W1}")


def check_C18_alpha_beta():
    g1, g2 = sp.simplify(-ALPHA), sp.simplify(BETA)
    k2 = sp.factor((ALPHA - BETA) * (ALPHA + BETA))  # S88 eq. (8e) for N = 1
    ok = sp.simplify(k2 - (g1**2 - g2**2)) == 0
    return report(18, ok, "S88 -alpha = gamma1, beta = gamma2, k^2 = gamma1^2 - gamma2^2",
                  f"gamma1 = {sp.expand(g1)}, gamma2 = {sp.expand(g2)}, k^2 = {k2}")


def check_C19_eigenvector():
    """G+/G- of the exp(-k tau) mode equals Toon's Gamma = (g1 - lambda)/g2 (eq. 22); 30-digit spot values."""
    g1, g2 = -ALPHA, BETA
    k = sp.sqrt(g1**2 - g2**2)
    ratio = -BETA / (ALPHA - k)
    gam = (g1 - k) / g2
    errs = [abs(sp.N((ratio - gam).subs({w: a, g: b}), 30)) for a, b in ((sp.Rational(3, 10), sp.Rational(1, 5)), (sp.Rational(9, 10), sp.Rational(3, 4)),
                                                                      (sp.Rational(1, 2), sp.Rational(-3, 10)))]
    return report(19, max(errs) < 1e-25, "S88 eigenvector ratio = Toon Gamma", "below 1e-25 at 3 rational points (30 digits)")


def check_C20_nstr2_closure():
    """NSTR = 2 is MW eqs. (37)-(38) with mu1 = 1/2, beta1 = 1/2 - 3g/8; it is not Toon's hemispheric mean."""
    b1d = sp.simplify(D(MU1, -MU1) / w)
    a, b = gq(MU1, b1d)
    same = sp.simplify(a + ALPHA) == 0 and sp.simplify(b - BETA) == 0
    dh = (sp.simplify(-ALPHA - (2 - w * (1 + g))), sp.simplify(BETA - w * (1 - g)))
    ok = same and dh == (w * g / 4, w * g / 4)
    return report(20, ok, "NSTR=2 = MW eqs. 37-38 at mu1=1/2; minus Toon HM", f"beta1 = {b1d}; (g1, g2) - HM = {dh}")


def check_C21_conservative_limit():
    """MW eq. (23): g1 - g2 = (1 - w)/mu1 with mu1 free of w, for every printed row (Toon eq. 18)."""
    out = []
    for name, src, row in PRINTED:
        r = sp.simplify((row["g1"] - row["g2"]) / (1 - w))
        out.append((name, src, r, not r.has(w)))
    ok = all(x[3] for x in out)
    return report(21, ok, "g1 - g2 = (1-w)/mu1 for all rows", "; ".join(f"{a} ({b}): 1/mu1 = {c}" for a, b, c, _ in out))


def check_C22_g3_plus_g4():
    """MW eq. (21): g3 + g4 = 1 for the DERIVED beam coefficients of every closure that has them, and for the one row
    that prints g4 (quadrature, MW eq. 42). The derived g4 is integrated or read independently of g3 (derive())."""
    sums = {name: sp.simplify(d["g3"] + d["g4"]) for name, d in DERIVED.items() if "g3" in d}
    printed = [sp.simplify(row["g3"] + row["g4"]) for _, _, row in PRINTED if "g4" in row]
    ok = len(sums) == 7 and all(v == 1 for v in sums.values()) and all(v == 1 for v in printed)
    return report(22, ok, "g3 + g4 = 1", f"derived for {len(sums)} closures: "
                  + ", ".join(f"{k} {v}" for k, v in sums.items()) + f"; printed g4 rows: {printed}")


def main():
    res = check_rows()
    for f in (check_C11_hm_is_hconst, check_C12_quadrature_general, check_C13_delta_function_general,
              check_C14_hybrid_limits, check_C15_eddington_g3, check_C16_negative_control,
              check_C17_double_gauss_node, check_C18_alpha_beta, check_C19_eigenvector, check_C20_nstr2_closure,
              check_C21_conservative_limit, check_C22_g3_plus_g4):
        res.append(f())
    nfail = res.count(False)
    print(f"check_ch02_closures: {len(res) - nfail} of {len(res)} claims pass")
    return nfail


if __name__ == "__main__":
    sys.exit(main())
