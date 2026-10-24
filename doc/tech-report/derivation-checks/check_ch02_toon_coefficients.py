"""ch02 check: the two-stream coefficients pyharp's Toon solver evaluates equal the published table entries.

What is checked. The shortwave kernel (src/rtsolver/toon_mckay89_shortwave_impl.h, toon_mckay89_shortwave) and the
longwave kernel (src/rtsolver/toon_mckay89_longwave_impl.h, toon_mckay89_longwave) are read as text. Each cited
assignment is found by its left-hand side (it must occur exactly once), its right-hand side is translated to sympy
by a fixed token map, and the difference to the reference expression is simplified to 0. References: Toon et al.
(1989, JGR 94, 16287, doi:10.1029/jd094id13p16287) Table 1, eqs. (21)-(24), (27) and Table 3; Wiscombe (1977,
J. Atmos. Sci. 34, 1408, doi:10.1175/1520-0469(1977)034<1408:tdmrya>2.0.co;2) eqs. (14), (15), (20) with M = 1.
C24 locates the single-scattering-albedo clamp lines of RadiationBandImpl::forward (src/radiation/radiation_band.cpp)
as text; a text match cannot tell a working clamp from a disabled one, so the clamp's effect is measured by
check_ch02_clamp_pyharp.py.

Mirrors pyharp at the code pin (code_pin.yml). The source tree is $PYHARP_WT if set, else the repository that holds
this report, whose src/ is the pin's on the tech-report branch. The check does not import or build pyharp.
Needs sympy. Run: python3 check_ch02_toon_coefficients.py   (any directory; exits with the number of failures)
"""

import hashlib
import os
import re
import sys
from pathlib import Path

import sympy as sp

def pyharp_root():
    """The pyharp source tree: $PYHARP_WT if set; else the repository that holds this report (this file sits at
    doc/tech-report/derivation-checks/, three levels below it). A copy elsewhere must set PYHARP_WT."""
    if os.environ.get("PYHARP_WT"):
        return Path(os.environ["PYHARP_WT"])
    up = Path(__file__).resolve().parents
    if len(up) < 4 or not (up[3] / "src" / "rtsolver").is_dir():
        sys.exit(f"{Path(__file__).name}: no pyharp tree found three levels above this file; set PYHARP_WT")
    return up[3]


ROOT = pyharp_root()
SW = "src/rtsolver/toon_mckay89_shortwave_impl.h"
LW = "src/rtsolver/toon_mckay89_longwave_impl.h"
RB = "src/radiation/radiation_band.cpp"

W, G, TAU, w, g, mu0, F0, lam, a = sp.symbols("W G tau omega g mu0 F0 lambda a", positive=True)
xk1, xk2, g1s, g2s, g3s, g4s, den = sp.symbols("xk1 xk2 g1 g2 g3 g4 denom")
r3 = sp.sqrt(3)
TOK = [(r"W_IN\(i\)", "W"), (r"G_IN\(i\)", "G"), (r"DTAU_IN\(i\)", "tau"), (r"\bg_sq\b", "(G**2)"),
       (r"\bsqrt3d2\b", "(sqrt(3)/2)"), (r"\bsqrt3\b", "sqrt(3)"), (r"\bw0\[[ikn]\]", "omega"),
       (r"\bhg\[[ikn]\]", "g"), (r"\bmu_zm\[i\]", "mu0"), (r"\bF0_in\b", "F0"), (r"\bubari\b", "(1/2)"),
       (r"\balp\[[kn]\]", "a"), (r"\bxk1\[n\]", "xk1"), (r"\bxk2\[n\]", "xk2"), (r"\btwopi\b", "(2*pi)"),
       (r"\bcommon_den\b", "(1 + a)")]
LOC = dict(W=W, G=G, tau=TAU, omega=w, g=g, mu0=mu0, F0=F0, a=a, xk1=xk1, xk2=xk2, g1=g1s, g2=g2s, g3=g3s,
           g4=g4s, denom=den, lam=lam, sqrt=sp.sqrt, pi=sp.pi)


def find(path, lhs, parse=True):
    """(text, sympy RHS) of the one assignment in `path` whose stripped line starts with `lhs =` (or with `lhs`
    itself when it already holds ` = `, to pick one of several assignments to the same variable)."""
    hits = [s.strip() for s in (ROOT / path).read_text().splitlines() if s.strip().startswith(lhs if " = " in lhs else lhs + " =")]
    assert len(hits) == 1, f"{path}: {len(hits)} lines start with {lhs!r} ="
    if not parse:
        return hits[0], None
    e = hits[0].split("=", 1)[1].rstrip(";").strip()
    for pat, rep in TOK:
        e = re.sub(pat, rep, e)
    return hits[0], sp.nsimplify(sp.sympify(e, locals=LOC), rational=True)


def report(n, ok, label, detail):
    print(f"[C{n}] {'PASS' if ok else 'FAIL'} {label}: {detail}")
    return bool(ok)


def same(n, label, path, lhs, ref, subs=None):
    txt, e = find(path, lhs)
    d = sp.simplify((e - ref).subs(subs or {}))
    return report(n, d == 0, label, f"`{txt}`  minus reference = {d}")


F = G**2                                   # Wiscombe eq. (15), M = 1, HG moments: f = chi_2 = g^2
TQ = dict(g1=r3 * (2 - w * (1 + g)) / 2, g2=w * r3 * (1 - g) / 2, g3=(1 - r3 * g * mu0) / 2)  # Toon Table 1
H1, H2 = 2 - w * (1 + g), w * (1 - g)       # Toon Table 1, hemispheric mean
WPAR = (1 - a**2) / (1 - a**2 * g)          # a^2 = (1-w)/(1-w g)  <=>  w = (1-a^2)/(1-a^2 g)
U = sp.simplify(1 - WPAR * g)               # with u = 1 - w g: g1 = u(1+a^2), g2 = u(1-a^2), lambda = 2 a u


def checks():
    r = [same(1, "SW scaled omega = Wiscombe eq. 20b", SW, "w0[i]", (1 - F) * W / (1 - W * F)),
         same(2, "SW scaled tau = Wiscombe eq. 20a", SW, "dtau[i]", (1 - W * F) * TAU),
         same(3, "SW scaled g = Wiscombe eq. 14", SW, "hg[i]", (G - F) / (1 - F)),
         same(4, "SW gamma1 = Toon Table 1 quadrature", SW, "T g1", TQ["g1"]),
         same(5, "SW gamma2 = Toon Table 1 quadrature", SW, "T g2", TQ["g2"]),
         same(6, "SW gamma3 = Toon Table 1 quadrature", SW, "T g3", TQ["g3"]),
         same(7, "SW gamma4 = 1 - gamma3 (Table 1 footnote)", SW, "T g4", 1 - g3s),
         same(8, "SW lambda = Toon eq. 21", SW, "T lam", sp.sqrt(g1s**2 - g2s**2)),
         same(9, "SW Gamma = Toon eq. 22", SW, "gam[i]", (g1s - lam) / g2s),
         same(10, "SW denominator of eqs. 23-24", SW, "T denom", lam**2 - 1 / mu0**2),
         same(11, "SW C+ amplitude = Toon eq. 23 (F0 = pi F_s)", SW, "Ap[i]",
              w * F0 * ((g1s - 1 / mu0) * g3s + g4s * g2s) / den),
         same(12, "SW C- amplitude = Toon eq. 24", SW, "Am[i]", w * F0 * ((g1s + 1 / mu0) * g4s + g2s * g3s) / den)]
    txt, e = find(LW, "alp[k]")
    r.append(report(13, sp.simplify(e**2 - (H1 - H2) / (H1 + H2)) == 0, "LW a^2 = (g1-g2)/(g1+g2), Toon HM",
                    f"`{txt}`"))
    txt, e = find(LW, "lam[k]")
    r.append(report(14, sp.simplify((e**2).subs(a**2, (1 - w) / (1 - w * g)) - (H1**2 - H2**2)) == 0,
                    "LW lambda^2 = g1^2 - g2^2 (Toon eq. 21)", f"`{txt}`"))
    txt, e = find(LW, "gam[k]")
    ok = (sp.simplify(H1.subs(w, WPAR) - U * (1 + a**2)) == 0 and sp.simplify(H2.subs(w, WPAR) - U * (1 - a**2)) == 0
          and sp.simplify((H1.subs(w, WPAR) - 2 * a * U) / H2.subs(w, WPAR) - e) == 0)
    r.append(report(15, ok, "LW Gamma = (g1-lambda)/g2 (Toon eq. 22), parametrised by a", f"`{txt}`"))
    r.append(same(16, "LW 1/(gamma1+gamma2) of Toon eq. 27", LW, "term[k]", 1 / (H1 + H2)))
    for n, lhs, sgn in ((17, "Cpm1[k]", 1), (18, "Cmm1[k]", -1)):
        txt = find(LW, lhs, parse=False)[0]
        r.append(report(n, txt == f"{lhs} = B0[k] {'+' if sgn > 0 else '-'} B1[k] * term[k];",
                        f"LW C{'+' if sgn > 0 else '-'}(0) = Toon eq. 27 divided by 2 pi mu1 = pi", f"`{txt}`"))
    r.append(same(19, "LW Table 3 offset 1/(g1+g2) - mu1, mu1 = 1/2", LW, "T term_val", 1 / (H1 + H2) - sp.Rational(1, 2)))
    gam, lmb = (1 - a) / (1 + a), 2 * a * U
    t3 = {"g[n] = twopi": (20, "G", sp.pi * xk1 * (2 - lmb)), "h[n] = twopi": (21, "H", sp.pi * xk2 * gam * (lmb + 2)),
          "xj[n] = twopi": (22, "J", sp.pi * xk1 * gam * (lmb + 2)), "xk[n] = twopi": (23, "K", sp.pi * xk2 * (2 - lmb))}
    for lhs, (n, nm, ref) in t3.items():
        txt, e = find(LW, lhs)
        d = sp.simplify(e.subs(w, WPAR) - ref)
        r.append(report(n, d == 0, f"LW Toon Table 3 {nm} with (Y1 +- Y2) -> pi xk1, pi xk2", f"`{txt}`  diff = {d}"))
    src = (ROOT / RB).read_text()
    ok = ("prop.scalar_type() == torch::kFloat64 ? 1.0e-12 : 1.0e-6;" in src
          and "prop.select(-1, disort::ISS).clamp_max_(1.0 - ssa_margin);" in src)
    r.append(report(24, ok, "SSA clamp lines 1e-12 (f64) / 1e-6 (f32) present in RadiationBandImpl::forward (text only;"
                    " the effect, and the absence of a cap in the Toon kernels, is measured by check_ch02_clamp_pyharp.py)",
                    f"band clamp lines present: {ok}"))
    sw_lines = [find(SW, k, parse=False)[0] for k in ("w0[i]", "dtau[i]", "hg[i]")]
    lw_text = [s.strip() for s in (ROOT / LW).read_text().splitlines()]
    r.append(report(25, all(x in lw_text for x in sw_lines), "LW optional delta-Eddington (delta_eddington_lw) uses"
                    " the SW scaling lines verbatim", f"{sum(x in lw_text for x in sw_lines)} of 3 lines"))
    return r


def main():
    for p in (SW, LW, RB):
        print(f"source {p} sha256 {hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}")
    res = checks()
    nfail = res.count(False)
    print(f"check_ch02_toon_coefficients: {len(res) - nfail} of {len(res)} claims pass")
    return nfail


if __name__ == "__main__":
    sys.exit(main())
