#!/usr/bin/env python3
"""Chapter 4 executable check: the Toon et al. (1989) two-stream solver of pyharp, run through pyharp itself.

What is checked (labels as printed; the chapter cites them):
  [C1]-[C3] Shortwave (`ToonMcKay89`, no `planck` flag) against an independent 40-digit solution of the same
            two-stream ODE (quadrature closure, delta-Eddington scaling), on a 648-case grid of optical depth,
            single-scattering albedo, asymmetry, beam cosine, surface albedo and sublayer count.
  [C4]      Shortwave at the lambda*mu0 = 1 resonance guard.
  [C5]      Longwave (`planck`, `hard_surface`) isothermal column with full Planck at the top: F = pi*B at every
            level and layer midpoint.
  [C6]      Toon et al. (1989) Table 4, cases 1-5: the printed two-stream ("approximate") fluxes.
  [K1]-[K6] CANDIDATE defects. Each prints XFAIL when the candidate behaviour is reproduced and XPASS when it is
            not; candidates never change the exit status.

How to run: `python3 toon_pyharp_check.py` with pyharp importable (it imports pyharp, torch and mpmath).
`python3 toon_pyharp_check.py --data <file.csv>` also writes the single-bottom-layer error sweep that the chapter's
data figure reads (lambda*dtau from 5 to 60).
Exit status: the number of failed core checks [C1]-[C6].
Deterministic: fixed grids, torch.manual_seed(0), float64, one thread.

The reference [C1]-[C4] integrates d/dtau [F+, F-, e^{-tau/mu0}] = M [F+, F-, e^{-tau/mu0}] with the 3x3 matrix
exponential in mpmath (no eigen-decomposition, no tridiagonal system), so it shares no algebra with the code
beyond the two-stream equations themselves (Toon et al. 1989 eqs. 11-14, Table 1).
"""
import itertools
import math
import platform
import sys

import mpmath as mp
import numpy
import torch
import pyharp

torch.set_default_dtype(torch.float64)
torch.manual_seed(0)
torch.set_num_threads(1)


# ------------------------------------------------------------------------------------------------- reference
def delta_eddington(w, g):
    """(w', tau'/tau, g') for truncation fraction f = g^2 (Joseph et al. 1976)"""
    f = g * g
    return (1 - f) * w / (1 - w * f), 1 - w * f, g / (1 + g)


def quadrature_gammas(wp, gp, mu0):
    """Toon et al. (1989) Table 1, quadrature row"""
    s3 = mp.sqrt(3)
    g1 = s3 / 2 * (2 - wp * (1 + gp))
    g2 = s3 / 2 * wp * (1 - gp)
    g3 = (1 - s3 * gp * mu0) / 2
    return g1, g2, g3, 1 - g3


def reference(tau, w, g, mu0, A, F0, fracs, dps=40):
    """(F+, F- + F_dir) at fractional depths `fracs` (0 = top) of a homogeneous slab over a Lambertian surface"""
    with mp.workdps(dps):
        w, g, mu0, A, F0, tau = map(mp.mpf, (w, g, mu0, A, F0, tau))
        wp, tf, gp = delta_eddington(w, g)
        tp = tf * tau
        g1, g2, g3, g4 = quadrature_gammas(wp, gp, mu0)
        M = mp.matrix([[g1, -g2, -g3 * wp * F0], [g2, -g1, g4 * wp * F0], [0, 0, -1 / mu0]])
        E = lambda t: mp.expm(M * t)
        ET = E(tp)
        ya = ET * mp.matrix([0, 0, 1])          # response to the beam with F+(0) = 0
        yb = ET * mp.matrix([1, 0, 0])          # response to F+(0) = 1
        direct = F0 * mu0 * mp.e ** (-tp / mu0)
        x = (A * direct - ya[0] + A * ya[1]) / (yb[0] - A * yb[1])   # F+(T) = A (F-(T) + F_dir(T))
        out = []
        for fr in fracs:
            y = E(tp * mp.mpf(fr)) * mp.matrix([x, 0, 1])
            out.append((float(y[0]), float(y[1] + F0 * mu0 * mp.e ** (-tp * mp.mpf(fr) / mu0))))
        return out


def toon_sw(dtau_top_down, w, g, mu0, A, F0, flags=""):
    """pyharp shortwave fluxes, external order (index 0 = bottom level), channels [up, down, mid-up, mid-down]"""
    o = pyharp.ToonMcKay89Options()
    o.wave_lower([1.0])
    o.wave_upper([2.0])
    if flags:
        o.flags(flags)
    n = len(dtau_top_down)
    p = torch.zeros(1, 1, n, 3)
    p[..., 0] = torch.tensor(dtau_top_down[::-1])
    p[..., 1] = w
    p[..., 2] = g
    return pyharp.ToonMcKay89(o)(p, fbeam=torch.full((1, 1), float(F0)), umu0=torch.tensor([float(mu0)]),
                                 albedo=torch.full((1, 1), float(A)))[0, 0]


def sw_error(tau, w, g, mu0, A, N, dps=40):
    """max over levels and both channels of |pyharp - reference| / (F0 mu0), F0 = 1, N equal sublayers"""
    fl = toon_sw([tau / N] * N, w, g, mu0, A, 1.0)
    ref = reference(tau, w, g, mu0, A, 1.0, [1 - k / N for k in range(N + 1)], dps)
    return max(max(abs(fl[k, 0].item() - ref[k][0]), abs(fl[k, 1].item() - ref[k][1]))
               for k in range(N + 1)) / mu0


def lam_quadrature(w, g):
    wp, _, gp = delta_eddington(w, g)
    g1 = math.sqrt(3) / 2 * (2 - wp * (1 + gp))
    g2 = math.sqrt(3) / 2 * wp * (1 - gp)
    return math.sqrt(g1 * g1 - g2 * g2)


results = []


def core(label, name, value, tol, reason):
    ok = value <= tol
    print(f"[{label}] {'PASS' if ok else 'FAIL'} {name}: {value:.2e} (tol {tol:.1e}: {reason})")
    results.append(ok)


def candidate(label, name, reproduced, numbers):
    print(f"[{label}] {'XFAIL' if reproduced else 'XPASS'} CANDIDATE {name}: {numbers}")


# ------------------------------------------------------------------------------------------------- C1-C3
def check_C1_C3():
    worst = {1: (0.0, None), 7: (0.0, None), 50: (0.0, None)}
    for tau, w, g, mu0, A, N in itertools.product([0.01, 0.3, 3.0, 10.0], [0.3, 0.9, 0.999], [0.0, 0.5, 0.85],
                                                 [0.2, 0.6, 1.0], [0.0, 0.4], [1, 7, 50]):
        e = sw_error(tau, w, g, mu0, A, N)
        if e >= worst[N][0]:
            worst[N] = (e, (tau, w, g, mu0, A))
    reason = {1: "one layer with lambda*tau up to 14.5 carries e^{lambda tau} eps ~ 4e-10 cancellation",
              7: "round-off of a 14-row tridiagonal solve", 50: "round-off of a 100-row tridiagonal solve"}
    for i, (N, tol) in enumerate([(1, 1e-9), (7, 1e-12), (50, 1e-12)]):
        core(f"C{i + 1}", f"SW vs 40-digit ODE, {N} sublayer(s), 216 cases, max|dF|/(F0 mu0) "
             f"[worst at tau,w,g,mu0,A = {worst[N][1]}]", worst[N][0], tol, reason[N])


# ------------------------------------------------------------------------------------------------- C4
def check_C4():
    worst = 0.0
    for w, g, tau, N in [(0.5, 0.0, 2.0, 10), (0.3, 0.2, 1.0, 10), (0.2, 0.5, 4.0, 20)]:
        lam = lam_quadrature(w, g)
        for d in [0.0, 1e-12, 1e-9]:
            mu0 = (1 + d) / lam
            fl = toon_sw([tau / N] * N, w, g, mu0, 0.0, 1.0)
            e = sw_error(tau, w, g, mu0, 0.0, N) if torch.isfinite(fl).all() else float("inf")
            worst = max(worst, e)
    core("C4", "SW at lambda*mu0 = 1 (offsets 0, 1e-12, 1e-9; 3 media), max|dF|/(F0 mu0)", worst, 5e-8,
         "the guard moves mu0 by sqrt(eps) = 1.5e-8; 5e-8 allows a factor 3")


# ------------------------------------------------------------------------------------------------- C5 / K2
NW, NC, NL = 4, 64, 40
WLO, WHI = [100., 500., 1000., 2000.], [500., 1000., 2000., 3000.]
PROP = torch.zeros(NW, NC, NL, 3)
PROP[..., 0] = 10 ** (4 * torch.rand(NW, NC, NL) - 3)
PROP[..., 1] = torch.rand(NW, NC, NL) * 0.99
PROP[..., 2] = torch.rand(NW, NC, NL) * 0.9
TEMF = torch.full((NC, NL + 1), 250.0)
_col = lambda v: torch.tensor(v).unsqueeze(-1).unsqueeze(-1)
PIB = math.pi * pyharp.bbflux_wavenumber(_col(WLO), _col(WHI), TEMF)


def lw_isothermal_error(flags, albedo):
    o = pyharp.ToonMcKay89Options()
    o.wave_lower(WLO)
    o.wave_upper(WHI)
    o.flags(flags)
    o.top_emission_flag(1)
    f = pyharp.ToonMcKay89(o)(PROP, temf=TEMF, albedo=torch.full((NW, NC), albedo))
    lev = (f[..., :2] / PIB.unsqueeze(-1) - 1).abs().max().item()
    mid = (f[..., 1:, 2:] / PIB[..., 1:].unsqueeze(-1) - 1).abs().max().item()   # slot 0 holds no midpoint
    return max(lev, mid)


def check_C5():
    e = max(lw_isothermal_error(fl, a) for fl, a in [("planck,hard_surface", 0.0), ("planck,hard_surface", 0.3),
                                                     ("planck,hard_surface,delta_eddington_lw", 0.3)])
    core("C5", "LW isothermal column, F = pi*B at levels and midpoints, hard surface albedo 0 and 0.3, "
         "with and without delta_eddington_lw, 4 bands x 64 columns x 40 layers, max|F/(pi B) - 1|", e, 1e-13,
         "an exact zero of the tridiagonal right-hand side; 1e-13 allows ~450 ulp")


# ------------------------------------------------------------------------------------------------- C6
TABLE4 = [  # case, mu0, tau, w, g, F+(0) approx, F-(tau) approx, F+(0) exact, F-(tau) exact (Toon 1989 Table 4)
    (1, 1.0, 1.0, 1.0, 0.794, 0.174, 1.812, 0.173, 1.813), (2, 1.0, 1.0, 0.9, 0.794, 0.133, 1.522, 0.124, 1.516),
    (3, 0.5, 1.0, 0.9, 0.794, 0.221, 0.864, 0.226, 0.803), (4, 1.0, 64., 1.0, 0.848, 2.686, 0.455, 2.662, 0.480),
    (5, 1.0, 64., 0.9, 0.848, 0.376, 0.000, 0.376, 0.000)]


def check_C6():
    worst = 0.0
    for case, mu0, tau, w, g, up_ap, dn_ap, up_ex, dn_ex in TABLE4:
        N = 64 if tau > 10 else 1
        fl = toon_sw([tau / N] * N, min(w, 1 - 1e-12), g, mu0, 0.0, math.pi)   # Fs = 1: F0 = pi
        up = fl[N, 0].item()
        dn = fl[0, 1].item() - math.pi * mu0 * math.exp(-tau / mu0)            # diffuse: minus the unscaled beam
        worst = max(worst, abs(up - up_ap), abs(dn - dn_ap))
        print(f"[C6.{case}] F+(0) {up:.4f} (paper {up_ap:.3f}, exact {up_ex:.3f}); "
              f"F-(tau) {dn:.4f} (paper {dn_ap:.3f}, exact {dn_ex:.3f})")
    core("C6", "Toon 1989 Table 4 cases 1-5, max |pyharp - printed approximate value| (w0 = 1 entered as "
         "1 - 1e-12; tau = 64 split into 64 layers)", worst, 1.5e-3, "the paper prints 3 decimals: 5e-4 rounding "
         "plus 1e-3 margin")


# ------------------------------------------------------------------------------------------------- candidates
def candidates():
    a = toon_sw([0.1] * 30, 0.9, 0.5, 0.6, 0.2, 1.0)
    b = toon_sw([0.1] * 30, 0.9, 0.5, 0.6, 0.2, 1.0, "zenith_correction")
    d = (a - b).abs().max().item()
    candidate("K1", "zenith_correction has no effect on the output", torch.equal(a, b),
              f"max|F(flag on) - F(flag off)| = {d:.1e}, bitwise equal = {torch.equal(a, b)}")

    e = lw_isothermal_error("planck", 0.3)
    candidate("K2", "LW non-hard surface with albedo 0.3 breaks isothermal equilibrium", e > 1e-13,
              f"max|F/(pi B) - 1| = {e:.3f}")

    h, c, k = mp.mpf("6.62607015e-34"), mp.mpf("2.99792458e8"), mp.mpf("1.380649e-23")
    bnu = lambda nu, T: 2 * h * c ** 2 * (100 * nu) ** 3 / mp.expm1(h * c * 100 * nu / (k * T)) * 100
    T = 300.0
    rad = float(mp.quad(lambda n: bnu(n, T), [500, 800]))
    band = pyharp.bbflux_wavenumber(500.0, 800.0, torch.tensor([T])).item()
    candidate("K3", "bbflux band integral returns radiance, documented as flux", abs(band / (math.pi * rad) - 1) > 1e-3,
              f"500-800 cm-1, 300 K: bbflux / (pi int B_nu) = {band / (math.pi * rad):.4f}, "
              f"bbflux / int B_nu = {band / rad:.6f}")

    mono = pyharp.bbflux_wavenumber(667.0, 667.0, torch.tensor([T])).item() / float(bnu(667, T))
    candidate("K4", "bbflux with wn1 == wn2 is off by 1e-10", abs(mono - 1) > 1e-3,
              f"bbflux(667, 667, 300 K) / B_nu(667) = {mono:.4e}")

    lam = lam_quadrature(0.3, 0.0)
    errs, surf = [], []
    for tau in [15.0, 20.0, 25.0, 30.0, 40.0]:
        errs.append((lam * tau, sw_error(tau, 0.3, 0.0, 0.6, 0.0, 1, dps=120)))
    for thick in [30.0, 40.0]:
        for A in [0.0, 0.3]:
            coarse = toon_sw([0.5, 0.5, thick], 0.3, 0.0, 0.6, A, 1.0)
            fine = toon_sw([0.5, 0.5] + [thick / 400] * 400, 0.3, 0.0, 0.6, A, 1.0)
            surf.append((thick, A, coarse[0, 0].item(), coarse[0, 1].item(), fine[0, 0].item(), fine[0, 1].item(),
                         abs(coarse[-1, 0].item() - fine[-1, 0].item())))
    candidate("K5", "a thick bottom layer gives negative SW surface fluxes", max(e for _, e in errs) > 1e-9,
              "single layer w=0.3 g=0 mu0=0.6: " + ", ".join(f"lambda*tau={x:.0f}: {e:.0e}" for x, e in errs))
    for thick, A, cu, cd, fu, fd, top in surf:
        print(f"[K5.{int(thick)}.{A}] layers (0.5, 0.5, {thick:.0f}) top-down, A={A}: surface F+ {cu:.3e}, "
              f"F-+F_dir {cd:.3e}; same with the bottom layer in 400 sublayers: {fu:.1e}, {fd:.1e}; "
              f"TOA |dF+| {top:.1e}")

    e1 = sw_error(1.0, 1.0, 0.794, 1.0, 0.0, 1)
    e2 = sw_error(1.0, 1 - 1e-12, 0.794, 1.0, 0.0, 1)
    fl = toon_sw([1.0], 1.0, 0.794, 1.0, 0.0, math.pi)
    candidate("K6", "w0 = 1 exactly, passed straight to the kernel, gives wrong SW fluxes", e1 > 1e-9,
              f"tau=1 g=0.794 mu0=1: max|dF|/(F0 mu0) = {e1:.1e} at w0=1, {e2:.1e} at w0=1-1e-12; "
              f"Table 4 case 1 F+(0) = {fl[1, 0].item():.4f} (paper 0.174)")


def write_sweep(path):
    """[K5] sweep for the data figure: one SW layer (w=0.3, g=0, mu0=0.6, A=0), error vs lambda*dtau"""
    lam = lam_quadrature(0.3, 0.0)
    rows = []
    for x in [5, 10, 15, 20, 22.5, 25, 27.5, 30, 32.5, 35, 37.5, 40, 45, 50, 60]:
        rows.append((x, sw_error(x / lam, 0.3, 0.0, 0.6, 0.0, 1, dps=150)))
    with open(path, "w") as f:
        f.write("# toon_pyharp_check.py --data: one shortwave layer w=0.3 g=0 mu0=0.6 A=0 F0=1, N=1;\n")
        f.write(f"# pyharp {pyharp.__version__}, torch {torch.__version__}, mpmath {mp.__version__}, "
                f"Python {platform.python_version()}, CPU, float64\n")
        f.write("lambda_dtau,max_abs_dF_over_F0mu0\n")
        for x, e in rows:
            f.write(f"{x:g},{e:.3e}\n")


def main():
    if "--data" in sys.argv:
        write_sweep(sys.argv[sys.argv.index("--data") + 1])
    print(f"versions: pyharp {pyharp.__version__}, torch {torch.__version__}, mpmath {mp.__version__}, "
          f"numpy {numpy.__version__}, Python {platform.python_version()}")
    try:
        import pydisort
        print(f"pydisort {pydisort.__version__}")
    except ImportError:
        print("pydisort not importable")
    print("device: CPU, precision: float64, threads: 1")
    check_C1_C3()
    check_C4()
    check_C5()
    check_C6()
    candidates()
    fails = results.count(False)
    print(f"RESULT: {len(results) - fails}/{len(results)} core checks pass")
    return fails


if __name__ == "__main__":
    sys.exit(main())
