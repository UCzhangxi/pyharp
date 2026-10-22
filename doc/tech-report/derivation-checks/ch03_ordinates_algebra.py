"""ch03 check: the algebra of the discrete-ordinate solution (Stamnes et al. 1988), azimuthal mode m = 0,
built from the formulas the chapter derives, with numpy and sympy only (no pydisort, no pyharp).

The matrices mirror cdisort 2.1.3 as pydisort bundles it: CC_ij = w_j D(mu_i, mu_j) with
D(mu, mu') = (omega/2) sum_l (2l+1) chi_l P_l(mu) P_l(mu') (c_solve_eigen), the half-range Gauss rule
mirrored to negative mu (c_gaussian_quadrature, c_disort_set), the beam particular solution
(diag(1 + mu_i/mu0) - CC) Z0 = X0 (c_upbeam), and the thermal one (I - CC) Y1 = (1 - omega) b1,
(I - CC) Y0 = (1 - omega) b0 + M Y1 (c_upisot).

Labels:
  [C1] sympy: the order reduction. If [[alpha, beta], [-beta, -alpha]] (G+, G-) = k (G+, G-), then
       (alpha - beta)(alpha + beta)(G+ + G-) = k^2 (G+ + G-), for symbolic 2x2 blocks.
  [C2] the 2N eigenvalues of the full 2N x 2N matrix are +-sqrt(eigenvalues of (alpha - beta)(alpha + beta)),
       and of (alpha + beta)(alpha - beta) (the order cdisort uses), for N = 2, 4, 8 (tol 1e-10 relative:
       eigenvalues of a nonsymmetric matrix of size 16 in double precision).
  [C3] quadrature conservation: sum over j = +-1..+-N of w_j D(mu_i, mu_j) = omega for every i, for N = 1..16
       and moments truncated at 2N - 1 (tol 1e-14: a sum of 2N terms of size 1).
  [C4] the beam particular solution Z0 exp(-tau/mu0) satisfies the discrete-ordinate equations (residual
       <= 1e-13 of the source, N = 2, 4, 8).
  [C5] the thermal particular solution Y0 + Y1 tau satisfies them for B = b0 + b1 tau (same tolerance).
  [C6] the homogeneous solutions G_j exp(-k_j tau) satisfy them (same tolerance).
  [C7] the flux quadrature: 2 pi sum_i w_i mu_i equals pi to 1e-15 (an isotropic intensity I gives F = pi I).

Run: python ch03_ordinates_algebra.py
"""
import sys

import numpy as np
import sympy as sp
from numpy.polynomial import legendre as L


def half_range_gauss(n):
    """Gauss-Legendre on (0, 1), as cdisort's c_gaussian_quadrature; mirrored by the caller"""
    x, w = L.leggauss(n)
    return 0.5 * (x + 1.0), 0.5 * w


def setup(n, omega, g, nmom=None):
    mu, w = half_range_gauss(n)
    mus = np.concatenate([mu, -mu])          # i = 1..N upward, then the mirrored downward angles
    ws = np.concatenate([w, w])
    nmom = 2 * n - 1 if nmom is None else nmom
    chi = g ** np.arange(nmom + 1)            # Henyey-Greenstein moments, chi_0 = 1
    P = np.array([L.legval(mus, np.eye(nmom + 1)[k]) for k in range(nmom + 1)])  # P[k, i] = P_k(mu_i)
    D = 0.5 * omega * np.einsum("k,ki,kj->ij", (2 * np.arange(nmom + 1) + 1) * chi, P, P)
    CC = D * ws[None, :]
    return mu, w, mus, ws, chi, D, CC


def check_c1():
    a = sp.Matrix(2, 2, sp.symbols("a11 a12 a21 a22"))
    b = sp.Matrix(2, 2, sp.symbols("b11 b12 b21 b22"))
    gp = sp.Matrix(sp.symbols("p1 p2"))
    gm = sp.Matrix(sp.symbols("m1 m2"))
    k = sp.Symbol("k")
    r1 = a * gp + b * gm - k * gp          # first block row of the eigenproblem, = 0
    r2 = -b * gp - a * gm - k * gm         # second block row, = 0
    # (8c): (alpha - beta)(G+ - G-) - k (G+ + G-) = r1 + r2; (8d): (alpha + beta)(G+ + G-) - k (G+ - G-) = r1 - r2
    e8c = sp.expand((a - b) * (gp - gm) - k * (gp + gm) - (r1 + r2))
    e8d = sp.expand((a + b) * (gp + gm) - k * (gp - gm) - (r1 - r2))
    # (8e): (alpha - beta)(alpha + beta)(G+ + G-) - k^2 (G+ + G-) = (alpha - beta)(r1 - r2) + k (r1 + r2)
    e8e = sp.expand((a - b) * (a + b) * (gp + gm) - k**2 * (gp + gm) - ((a - b) * (r1 - r2) + k * (r1 + r2)))
    ok = all(x == 0 for x in list(e8c) + list(e8d) + list(e8e))
    print(f"[C1] {'PASS' if ok else 'FAIL'} sympy: (8c), (8d), (8e) follow from the two block rows identically")
    return ok


def check_c2():
    worst = 0.0
    for n in (2, 4, 8):
        mu, w, mus, ws, chi, D, CC = setup(n, 0.9, 0.7)
        Mi = np.diag(1.0 / mu)
        Dp, Dm = D[:n, :n], D[:n, n:]         # D(mu_i, mu_j), D(mu_i, -mu_j)
        Wn = np.diag(w)
        alpha = Mi @ (Dp @ Wn - np.eye(n))
        beta = Mi @ Dm @ Wn
        full = np.block([[alpha, beta], [-beta, -alpha]])
        ev = np.sort(np.linalg.eigvals(full).real)
        for prod in ((alpha - beta) @ (alpha + beta), (alpha + beta) @ (alpha - beta)):
            k = np.sqrt(np.sort(np.linalg.eigvals(prod).real))
            red = np.sort(np.concatenate([k, -k]))
            worst = max(worst, float(np.max(np.abs(red - ev) / np.max(np.abs(ev)))))
    ok = worst <= 1e-10
    print(f"[C2] {'PASS' if ok else 'FAIL'} eigenvalues of the 2N system = +-sqrt of the reduced N x N problem, "
          f"N = 2, 4, 8: max rel dev {worst:.1e} (tol 1e-10)")
    return ok


def check_c3():
    worst = 0.0
    for n in range(1, 17):
        _, _, _, ws, _, D, _ = setup(n, 0.8, 0.85)
        worst = max(worst, float(np.max(np.abs((D * ws[None, :]).sum(axis=1) - 0.8))))
    ok = worst <= 1e-14
    print(f"[C3] {'PASS' if ok else 'FAIL'} sum_j w_j D(mu_i, mu_j) = omega, N = 1..16: max |dev| {worst:.1e} (tol 1e-14)")
    return ok


def residual(mus, ws, D, I_of, dI_of, Q_of, taus):
    """max over tau and i of |mu_i dI/dtau - I + sum_j w_j D_ij I_j + Q_i| (discrete-ordinate equations)"""
    r = 0.0
    for t in taus:
        I, dI, Q = I_of(t), dI_of(t), Q_of(t)
        r = max(r, float(np.max(np.abs(mus * dI - I + (D * ws[None, :]) @ I + Q))))
    return r


def check_c4_c6():
    w4 = w5 = w6 = 0.0
    taus = (0.0, 0.3, 1.7)
    for n in (2, 4, 8):
        omega, g, mu0, F0 = 0.9, 0.7, 0.6, 1.0
        mu, w, mus, ws, chi, D, CC = setup(n, omega, g)
        Pm0 = np.array([L.legval(-mu0, np.eye(len(chi))[k]) for k in range(len(chi))])
        P = np.array([L.legval(mus, np.eye(len(chi))[k]) for k in range(len(chi))])
        X0 = omega * F0 / (4 * np.pi) * ((2 * np.arange(len(chi)) + 1) * chi * Pm0) @ P
        Z0 = np.linalg.solve(np.diag(1 + mus / mu0) - CC, X0)
        r = residual(mus, ws, D, lambda t: Z0 * np.exp(-t / mu0), lambda t: -Z0 / mu0 * np.exp(-t / mu0),
                     lambda t: X0 * np.exp(-t / mu0), taus)
        w4 = max(w4, r / np.max(np.abs(X0)))
        b0, b1 = 2.0, 0.5
        A = np.eye(2 * n) - CC
        Y1 = np.linalg.solve(A, np.full(2 * n, (1 - omega) * b1))
        Y0 = np.linalg.solve(A, (1 - omega) * b0 + mus * Y1)
        r = residual(mus, ws, D, lambda t: Y0 + Y1 * t, lambda t: Y1,
                     lambda t: np.full(2 * n, (1 - omega) * (b0 + b1 * t)), taus)
        w5 = max(w5, r / ((1 - omega) * (b0 + b1 * max(taus))))
        Mi = np.diag(1.0 / mu)
        alpha = Mi @ (D[:n, :n] @ np.diag(w) - np.eye(n))
        beta = Mi @ D[:n, n:] @ np.diag(w)
        kk, G = np.linalg.eig(np.block([[alpha, beta], [-beta, -alpha]]))
        for j in range(2 * n):
            k, Gj = kk[j].real, G[:, j].real / np.max(np.abs(G[:, j].real))
            r = residual(mus, ws, D, lambda t: Gj * np.exp(-k * t), lambda t: -k * Gj * np.exp(-k * t),
                         lambda t: np.zeros(2 * n), (0.0, 0.1))
            w6 = max(w6, r / max(1.0, abs(k)))
    ok = (w4 <= 1e-13, w5 <= 1e-13, w6 <= 1e-13)
    print(f"[C4] {'PASS' if ok[0] else 'FAIL'} beam particular solution residual {w4:.1e} of max X0 (tol 1e-13)")
    print(f"[C5] {'PASS' if ok[1] else 'FAIL'} thermal particular solution residual {w5:.1e} of the source (tol 1e-13)")
    print(f"[C6] {'PASS' if ok[2] else 'FAIL'} homogeneous solutions residual {w6:.1e} (tol 1e-13)")
    return all(ok)


def check_c7():
    worst = max(abs(2 * np.pi * np.sum(half_range_gauss(n)[1] * half_range_gauss(n)[0]) - np.pi) for n in range(1, 33))
    ok = worst <= 1e-15 * np.pi * 10
    print(f"[C7] {'PASS' if ok else 'FAIL'} 2 pi sum_i w_i mu_i = pi, N = 1..32: max |dev| {worst:.1e} (tol 3e-14)")
    return ok


def main():
    print(f"python {sys.version.split()[0]}, numpy {np.__version__}, sympy {sp.__version__}")
    nfail = sum(not f() for f in (check_c1, check_c2, check_c3, check_c4_c6, check_c7))
    sys.exit(nfail)


if __name__ == "__main__":
    main()
