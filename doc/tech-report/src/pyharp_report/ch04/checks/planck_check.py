#!/usr/bin/env python3
"""Check of the band-integrated Planck function of chapter 4 (scheme file `_planck.qmd`).

Ports `bbflux_wavenumber(wn1, wn2, temp)` of src/radiation/bbflux.cpp of pyharp at the pin of code_pin.yml line for
line into numpy (the scalar-temperature overload; the tensor overload has the same arithmetic) and compares it with
an mpmath quadrature of the Planck function B_nu.

  [C1] The band value is a radiance: the port equals int_{nu1}^{nu2} B_nu dnu [W m-2 sr-1] for four bands at
       300 K within 1e-4 relative (series truncation of the six-term exponential sum plus the old Stefan-Boltzmann
       constant), and is 1/pi of the hemispheric flux pi int B_nu dnu.
  [C2] Over the whole spectrum the port gives sigma_code T^4/pi with sigma_code = 5.67032e-8; relative to the
       exact sigma = 5.670374419e-8 that is -9.6e-6.
  [C3] The equal-edges branch uses c1 = 1.1911e-18. The radiance B_nu per wavenumber in W m-2 sr-1 (cm-1)-1 needs
       2 h c^2 x 1e8 = 1.19104e-8 (h c^2 in W m^2 sr-1, nu in cm-1): the branch is 1e-10 times B_nu.
  [C5] Error budget of [C1]: with the exact c2 = hc/k = 1.4387769 cm K and sigma, the same series is within 1.1e-5
       of the quadrature (the power series at v < 1.5) and within 1e-7 for bands with v > 1.5 (six-term tail); the code's c2 = 1.438786
       and sigma = 5.67032e-8 account for the rest.
  [C6] Truncation at the switch v = 1.5: the first neglected term of the power series,
       (15/pi^4)(5/66) v^13/(13 * 10!), and the m = 7 term of the exponential series, as fractions of sigma T^4/pi;
       and hc/k in cm K.
  [C4] The point overload `bbflux_wavenumber(wave, temp, ncol)` uses c1 = 1.19144e-8, c2 = 1.4388: within 3e-4 of
       B_nu at 667 cm-1, 300 K.

Run: python3 planck_check.py (numpy and mpmath, which sympy installs; about a second). Exit: number of failures.
"""
import math
import sys

import mpmath as mp
import numpy as np

H, C, KB = 6.62607015e-34, 2.99792458e8, 1.380649e-23
SIGMA_EXACT = 5.670374419e-8


def report(label, ok, text):
    ok = bool(ok)
    print(f"[{label}] {'PASS' if ok else 'FAIL'} {text}")
    return ok


def bnu(nu_cm, T):
    """Planck radiance per wavenumber, W m-2 sr-1 (cm-1)-1, in mpmath"""
    nu = mp.mpf(nu_cm) * 100
    return 2 * H * C ** 2 * nu ** 3 / mp.expm1(H * C * nu / (KB * T)) * 100


def band_port(wn1, wn2, T, C2=1.438786, SIGMA=5.67032e-8):
    """`bbflux_wavenumber(double wn1, double wn2, torch::Tensor temp)`, line for line, scalar T; C2 and SIGMA are
    the code's constants unless [C5] passes the exact ones"""
    VCUT = 1.5
    sigdpi = SIGMA / math.pi
    conc = 15.0 / math.pi ** 4
    c1 = 1.1911e-18
    A1, A2, A3, A4, A5, A6 = 1 / 3, -1 / 8, 1 / 60, -1 / 5040, 1 / 272160, -1 / 13305600
    if wn1 == wn2:
        arg = math.exp(-C2 * wn1 / T)
        return c1 * wn1 ** 3 * arg / (1 - arg)
    v = [C2 * wn1 / T, C2 * wn2 / T]
    smallv = 0
    p, d = [0.0, 0.0], [0.0, 0.0]
    for i in range(2):
        smallv += 1 if v[i] < VCUT else 0
        vsq = v[i] * v[i]
        p[i] = conc * vsq * v[i] * (A1 + v[i] * (A2 + v[i] * (A3 + vsq * (A4 + vsq * (A5 + vsq * A6)))))
        p[i] = p[i] if v[i] < VCUT else 0.0
        ex = math.exp(-v[i])
        exm = 1.0
        d[i] = 0.0
        for m in range(1, 7):
            mv = m * v[i]
            exm *= ex
            d[i] += exm * (6.0 + mv * (6.0 + mv * (3.0 + mv))) / m ** 4
        d[i] *= conc
        d[i] = d[i] if v[i] > VCUT else 0.0
    ans = p[1] - p[0] if smallv == 2 else (1.0 - p[0] - d[1] if smallv == 1 else d[0] - d[1])
    return ans * sigdpi * T ** 4


def check_C1_radiance():
    T = 300.0
    worst = 0.0
    rows = []
    for a, b in [(10, 350), (500, 800), (1000, 1100), (2000, 2500)]:
        ref = float(mp.quad(lambda n: bnu(n, T), [a, b]))
        got = band_port(float(a), float(b), T)
        worst = max(worst, abs(got / ref - 1))
        rows.append(f"{a}-{b}: {got / ref - 1:+.1e}")
    flux_ratio = band_port(500.0, 800.0, T) / (math.pi * float(mp.quad(lambda n: bnu(n, T), [500, 800])))
    ok = worst < 1e-4 and abs(flux_ratio - 1 / math.pi) < 1e-4
    return report("C1", ok, f"300 K, port / int B_nu - 1: {', '.join(rows)} (max {worst:.1e}); "
                  f"port / (pi int B_nu) = {flux_ratio:.4f} = 1/pi")


def check_C2_sigma():
    T = 300.0
    whole = band_port(1e-3, 1e6, T)
    rel = whole / (SIGMA_EXACT * T ** 4 / math.pi) - 1
    ok = abs(rel - (5.67032e-8 / SIGMA_EXACT - 1)) < 2e-6
    return report("C2", ok, f"whole spectrum / (sigma T^4/pi) - 1 = {rel:.2e}; sigma_code/sigma - 1 = "
                  f"{5.67032e-8 / SIGMA_EXACT - 1:.2e}")


def check_C3_equal_edges():
    T, nu = 300.0, 667.0
    ratio = band_port(nu, nu, T) / float(bnu(nu, T))
    c1_needed = 2 * H * C ** 2 * 1e8
    ok = abs(ratio - 1e-10) < 1e-13 and abs(c1_needed - 1.19104e-8) < 1e-12
    return report("C3", ok, f"equal-edges branch / B_nu(667 cm-1, 300 K) = {ratio:.4e}; 2hc^2 x 1e8 = "
                  f"{c1_needed:.5e} W m-2 sr-1 cm4 vs code 1.1911e-18")


def check_C4_point():
    T, nu = 300.0, 667.0
    c1, c2 = 1.19144e-5 * 1e-3, 1.4388
    got = c1 * nu ** 3 / (math.exp(c2 * nu / T) - 1.0)      # `bbflux_wavenumber(wave, temp, ncol)`
    rel = got / float(bnu(nu, T)) - 1
    return report("C4", abs(rel) < 3e-4, f"point overload / B_nu(667 cm-1, 300 K) - 1 = {rel:.1e}")


def check_C5_constants():
    T = 300.0
    c2x = H * C / KB * 100
    errs = []
    for a, b in [(10, 350), (500, 800), (1000, 1100), (2000, 2500)]:
        ref = float(mp.quad(lambda n: bnu(n, T), [a, b]))
        errs.append(band_port(float(a), float(b), T, C2=c2x, SIGMA=SIGMA_EXACT) / ref - 1)
    ok = abs(errs[0]) < 1.1e-5 and max(abs(e) for e in errs[1:]) < 1e-7   # six-term tail at v ~ 2.4: 7e-8
    return report("C5", ok, "exact c2 and sigma, port / int B_nu - 1: " + ", ".join(f"{e:+.1e}" for e in errs))


def check_C6_truncation():
    v = 1.5
    power = 15 / math.pi ** 4 * (5 / 66) * v ** 13 / (13 * math.factorial(10))
    m = 7
    mv = m * v
    expo = 15 / math.pi ** 4 * math.exp(-mv) * (mv ** 3 + 3 * mv ** 2 + 6 * mv + 6) / m ** 4
    c2x = H * C / KB * 100
    ok = 4e-8 < power < 6e-8 and 2e-6 < expo < 4e-6 and abs(c2x - 1.4387769) < 1e-7
    return report("C6", ok, f"at v = 1.5: next power-series term {power:.1e}, m = 7 exponential term {expo:.1e} "
                  f"(fractions of sigma T^4/pi); hc/k = {c2x:.7f} cm K")


def main():
    oks = [check_C1_radiance(), check_C2_sigma(), check_C3_equal_edges(), check_C4_point(), check_C5_constants(), check_C6_truncation()]
    print(f"RESULT: {sum(oks)}/{len(oks)} pass")
    return len(oks) - sum(oks)


if __name__ == "__main__":
    sys.exit(main())
