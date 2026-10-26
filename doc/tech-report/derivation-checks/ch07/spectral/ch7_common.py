"""Shared helpers for the chapter 7 spectral-integration checks.

Independent reference quantities are built here from CODATA-2018 SI constants
and scipy quadrature; nothing in this module calls pyharp.
"""

import numpy as np
from scipy import integrate

# CODATA 2018 / SI-2019 exact defining constants
H_PLANCK = 6.62607015e-34  # J s   (exact)
K_BOLTZ = 1.380649e-23  # J/K   (exact)
C_LIGHT = 2.99792458e8  # m/s   (exact)
# Stefan-Boltzmann from the exact constants
SIGMA_SB = (
    2.0 * np.pi**5 * K_BOLTZ**4 / (15.0 * H_PLANCK**3 * C_LIGHT**2)
)  # W m^-2 K^-4


def planck_wavenumber(nu_cm, temp):
    """Planck radiance B_nu(T).

    nu_cm : wavenumber [cm^-1]
    temp  : temperature [K]
    returns W m^-2 sr^-1 / cm^-1
    """
    nu_cm = np.asarray(nu_cm, dtype=float)
    nu_si = 100.0 * nu_cm  # m^-1
    x = H_PLANCK * C_LIGHT * nu_si / (K_BOLTZ * temp)
    # 2 h c^2 nu^3 / (exp(x) - 1) is per (m^-1); multiply by 100 for per cm^-1
    return 100.0 * 2.0 * H_PLANCK * C_LIGHT**2 * nu_si**3 / np.expm1(x)


def planck_band_integral(wn1, wn2, temp, epsabs=1e-16, epsrel=1e-13):
    """int_{wn1}^{wn2} B_nu(T) dnu  [W m^-2 sr^-1], by adaptive quadrature."""
    val, err = integrate.quad(
        planck_wavenumber, wn1, wn2, args=(temp,), epsabs=epsabs, epsrel=epsrel,
        limit=400,
    )
    return val, err


def planck_flux_band(wn1, wn2, temp):
    """pi * int B_nu dnu [W m^-2]: hemispheric blackbody flux in the band."""
    val, err = planck_band_integral(wn1, wn2, temp)
    return np.pi * val, np.pi * err


def relerr(a, b):
    return abs(a - b) / abs(b)
