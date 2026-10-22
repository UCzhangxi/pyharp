"""ch05: DISORT against the benchmark fluxes of Garcia & Siewert (1985), Table 22, and pyharp's Toon89 against the
approximate fluxes Toon et al. (1989) give for the same five problems in their Table 4.

Problems (Garcia & Siewert 1985, Table 21): Haze L (tau0 = 1) and Cloud C1 (tau0 = 64) phase functions, beam with
pi F = pi incident at mu0, no surface. Fluxes q+ (downward, beam included), q- (upward) and q = q+ - q- at
tau = 0, tau0/20, tau0/10, tau0/5, tau0/2, 3 tau0/4, tau0. Phase moments: pydisort.scattering_moments(n,
'haze-garcia-siewert' | 'cloud-garcia-siewert'), cdisort's c_getmom tables (the coefficients of G&S Tables 10 and
17). Table 22 is printed to 6 significant figures, so agreement cannot be shown below about 5e-6 relative.

Run: python3 check_ch05_gs85.py [--data DIR]. Exit status: the number of FAIL lines.
"""

import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch05_common as C  # noqa: E402
import pydisort  # noqa: E402

FR = np.array([0.0, 1 / 20, 1 / 10, 1 / 5, 1 / 2, 3 / 4, 1.0])
CASES = {1: ("haze-garcia-siewert", 1.0, 1.0, 1.0), 2: ("haze-garcia-siewert", 1.0, 0.9, 1.0),
         3: ("haze-garcia-siewert", 1.0, 0.9, 0.5), 4: ("cloud-garcia-siewert", 64.0, 1.0, 1.0),
         5: ("cloud-garcia-siewert", 64.0, 0.9, 1.0)}          # model, tau0, omega, mu0
# Garcia & Siewert 1985, Table 22 (p. 480): rows q+, q-, q at the depths FR * tau0
T22 = {
    1: [[3.14159, 3.13794, 3.13349, 3.12286, 3.07948, 3.03087, 2.96837],
        [1.73223e-1, 1.69570e-1, 1.65124e-1, 1.54494e-1, 1.11113e-1, 6.24993e-2, 0.0], [2.96837] * 7],
    2: [[3.14159, 3.12151, 3.10074, 3.05777, 2.92065, 2.79923, 2.67127],
        [1.23665e-1, 1.20901e-1, 1.17603e-1, 1.09841e-1, 7.88688e-2, 4.45453e-2, 0.0],
        [3.01793, 3.00061, 2.98314, 2.94793, 2.84178, 2.75469, 2.67127]],
    3: [[1.57080, 1.54485, 1.51680, 1.45804, 1.28063, 1.14320, 1.01588],
        [2.25487e-1, 2.19149e-1, 2.10953e-1, 1.91599e-1, 1.23848e-1, 6.40824e-2, 0.0],
        [1.34531, 1.32570, 1.30585, 1.26644, 1.15678, 1.07912, 1.01588]],
    4: [[3.14159, 3.55742, 3.56929, 3.29179, 2.24768, 1.37243, 4.79852e-1],
        [2.66174, 3.07757, 3.08944, 2.81194, 1.76783, 8.92573e-1, 0.0], [4.79852e-1] * 7],
    5: [[3.14159, 1.87572, 9.80914e-1, 2.33984e-1, 2.67761e-3, 6.38345e-5, 1.47334e-6],
        [3.75305e-1, 2.70485e-1, 1.51045e-1, 3.74253e-2, 4.31818e-4, 1.02904e-5, 0.0],
        [2.76629, 1.60524, 8.29869e-1, 1.96558e-1, 2.24579e-3, 5.35441e-5, 1.47334e-6]],
}
# Toon et al. 1989, Table 4 (p. 16,295): asymmetry used, and their approximate F+(0) (reflected) and F-(tau)
# (diffusely transmitted), printed to 3 decimals
T89_G = {1: 0.794, 2: 0.794, 3: 0.794, 4: 0.848, 5: 0.848}
T89_APPROX = {1: (0.174, 1.812), 2: (0.133, 1.522), 3: (0.221, 0.864), 4: (2.686, 0.455), 5: (0.376, 0.000)}
NSTR = [16, 32, 64, 128, 256]
NGATE = 128
TOL_REL = 2.0e-5        # 4 x the half-unit of the 6th significant figure of a value near 1 (5e-6)
TOL_T89 = 6.0e-4        # half-unit of the 3rd decimal (5e-4) plus 1e-4 for the table's own rounding of inputs


def disort_case(c, nstr):
    model, tau0, ssa, mu0 = CASES[c]
    dtau = np.diff(FR * tau0)[None, :]
    pm = np.broadcast_to(pydisort.scattering_moments(nstr, model).numpy(), (1, dtau.shape[1], nstr)).copy()
    f = C.run_disort_sw(nstr, dtau, np.full_like(dtau, ssa), pm, np.array([mu0]), np.array([0.0]), fbeam=math.pi)
    up, dn = f[0, ::-1, 0], f[0, ::-1, 1]
    return np.array([dn, up, dn - up])


def toon_case(c, g, ssa_margin):
    model, tau0, ssa, mu0 = CASES[c]
    dtau = np.diff(FR * tau0)[None, :]
    f = C.run_toon_sw(dtau, np.full_like(dtau, min(ssa, 1.0 - ssa_margin)), np.full_like(dtau, g),
                      np.array([mu0]), np.array([0.0]), fbeam=math.pi)
    up, dn = f[0, ::-1, 0], f[0, ::-1, 1]
    return np.array([dn, up, dn - up])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    a = ap.parse_args()
    print(C.version_line())
    print(C.env_line())
    ck = C.Checker()
    worst = 0.0
    for c, t in T22.items():
        t = np.array(t)
        worst = max(worst, float(np.abs(t[0] - t[1] - t[2]).max()))
    ck.check("Table 22 transcription: max |q+ - q- - q| over the 5 cases", worst, 1.5e-5)
    table = {}
    for n in NSTR:
        rb = []
        for c in CASES:
            q, t = disort_case(c, n), np.array(T22[c])
            m = t != 0
            rb.append(float((np.abs(q - t)[m] / np.abs(t[m])).max()))
        table[n] = rb
        ck.info(f"DISORT nstr={n} max rel diff vs Table 22, cases 1-5",
                " ".join(f"{x:.2e}" for x in rb) + f"; max {max(rb):.2e}")
    ck.check(f"DISORT nstr={NGATE} max rel diff vs Table 22 over all non-zero entries", max(table[NGATE]), TOL_REL)
    nhaze = next(n for n in NSTR if max(table[n][:3]) <= TOL_REL)
    ck.info(f"smallest nstr with the three haze cases within {TOL_REL:g}", f"{nhaze}")
    # Toon with the authors' own g; omega = 1 run at 1 - 1e-12, the margin RadiationBand applies in double
    wd = 0.0
    for c in CASES:
        model, tau0, ssa, mu0 = CASES[c]
        q = toon_case(c, T89_G[c], 1e-12)
        beam = math.pi * mu0 * math.exp(-tau0 / mu0)
        R, Td = q[1, 0], q[0, -1] - beam
        wd = max(wd, abs(R - T89_APPROX[c][0]), abs(Td - T89_APPROX[c][1]))
        ck.info(f"Toon case {c} (g={T89_G[c]})", f"R={R:.4f} [Toon89 {T89_APPROX[c][0]:.3f}], "
                f"Td={Td:.4f} [Toon89 {T89_APPROX[c][1]:.3f}]")
    ck.check("Toon vs Toon et al. 1989 Table 4 approximate values, max |diff|", wd, TOL_T89)
    # Toon error against the exact Table 22 values, g = chi_1 of the same moment table
    errs = {}
    for c in CASES:
        model, tau0, ssa, mu0 = CASES[c]
        g = float(pydisort.scattering_moments(16, model).numpy()[0])   # c_getmom rejects nmom < 2
        q, t = toon_case(c, g, 1e-12), np.array(T22[c])
        beam = math.pi * mu0 * math.exp(-tau0 / mu0)
        eR = abs(q[1, 0] - t[1, 0]) / t[1, 0]
        eT = abs((q[0, -1] - beam) - (t[0, -1] - beam)) / (t[0, -1] - beam)
        errs[c] = (eR, eT)
        ck.info(f"Toon case {c} (g={g:.4f}) vs Table 22", f"reflected {100 * eR:.2f} %, diffuse transmitted "
                f"{100 * eT:.2f} %")
    # omega = 1 exactly: the bare Toon kernel (no RadiationBand margin)
    q0, t4 = toon_case(4, float(pydisort.scattering_moments(16, CASES[4][0]).numpy()[0]), 0.0), np.array(T22[4])
    ck.expect_fail("Toon case 4 with omega = 1 exactly: |Td - Table 22|/Table 22",
                   abs(q0[0, -1] - t4[0, -1]) / t4[0, -1], 0.10)
    if a.data:
        os.makedirs(a.data, exist_ok=True)
        with open(os.path.join(a.data, "gs85.json"), "w") as f:
            json.dump({"nstr": NSTR, "rel": {str(n): table[n] for n in NSTR}, "tol": TOL_REL,
                       "toon_err": {str(c): errs[c] for c in errs}}, f, indent=1)
    sys.exit(ck.done("check_ch05_gs85"))


if __name__ == "__main__":
    main()
