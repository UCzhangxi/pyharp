#!/usr/bin/env python3
"""Tests for the Toon-McKay89 two-stream radiative transfer solver.

This test suite validates the ToonMcKay89 solver by:
  - Comparing with the analytical Beer-Lambert law for pure absorption.
  - Verifying physical consistency (positive fluxes, energy conservation).
  - Comparing shortwave and longwave fluxes against the DISORT multi-stream solver.

Level ordering convention (both Toon and DISORT with ``upward=True``):
  - level 0    = bottom of atmosphere (surface)
  - level nlyr = top of atmosphere (TOA)
  - flx[..., 0] = upward flux, flx[..., 1] = downward flux

Requires pyharp >= 1.9.0 and pydisort >= 1.5.0.
"""

import json
import math
import mpmath as mp
import subprocess
import sys
import torch
import pyharp
import pydisort

torch.set_default_dtype(torch.float64)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_toon_sw_pure_absorption():
    """Toon solver must reproduce the Beer-Lambert law for pure absorption.

    With w0=0 and zero surface albedo, the downward flux at each level follows
    ``fbeam * umu0 * exp(-(nlyr - k) * tau / umu0)`` exactly.
    """
    nwave = 3
    ncol = 1
    nlyr = 10
    nprop = 3
    tau = 0.1
    fbeam = 1000.0
    umu0 = 0.5
    wave_lo = [200.0, 500.0, 1000.0]
    wave_hi = [500.0, 1000.0, 2000.0]

    opt = pyharp.ToonMcKay89Options()
    opt.wave_lower(wave_lo)
    opt.wave_upper(wave_hi)
    toon = pyharp.ToonMcKay89(opt)

    bc = {
        "fbeam": torch.ones(nwave, ncol) * fbeam,
        "umu0":  torch.ones(ncol) * umu0,
        "albedo": torch.zeros(nwave,ncol)
    }

    prop = torch.zeros(nwave,ncol,nlyr,nprop)
    prop[:,:,:,0] = tau  # optical depth

    result = toon(prop, **bc)
    toon_out = {
        "dn": result[0,0,:,1].tolist(),
        "up": result[0,0,:,0].tolist()
    }

    # Analytical Beer-Lambert law: level k traverses (nlyr-k) layers from TOA
    expected_dn = [
        fbeam * umu0 * math.exp(-(nlyr - k) * tau / umu0)
        for k in range(nlyr + 1)
    ]
    print("Level | Toon dn | Expected dn")
    print("-----------------------------")

    for k in range(nlyr + 1):
        print(f"{k:5d} | {toon_out['dn'][k]:8.4f} | {expected_dn[k]:11.4f}")
        assert abs(toon_out["dn"][k] - expected_dn[k]) < 1e-8, (
            f"Toon Beer-Lambert mismatch at level {k}"
        )

        assert abs(toon_out["up"][k]) < 1e-10, (
            f"Non-zero Toon upward flux at level {k} for pure absorption"
        )

def test_toon_sw_scattering():
    """Toon fluxes must satisfy energy conservation for shortwave scattering.

    This test verifies physical consistency of the two-stream approximation:
      - All fluxes are non-negative.
      - Reflected flux at TOA does not exceed the incident solar flux.
      - Surface downward flux does not exceed the incident solar flux.

    Each (w0, g) case runs in its own subprocess with a single ToonMcKay89
    instance to avoid CPU dispatch state conflicts.
    """
    nwave = 3
    ncol = 1
    nlyr = 10
    nprop = 3
    tau = 0.1
    fbeam = 1000.0
    umu0 = 0.5
    incident = fbeam * umu0
    wave_lo = [200.0, 500.0, 1000.0]
    wave_hi = [500.0, 1000.0, 2000.0]

    opt = pyharp.ToonMcKay89Options()
    opt.wave_lower(wave_lo)
    opt.wave_upper(wave_hi)
    toon = pyharp.ToonMcKay89(opt)

    prop = torch.zeros(nwave,ncol,nlyr,nprop)
    prop[:,:,:,0] = tau  # optical depth

    bc = {
        "fbeam": torch.ones(nwave,ncol) * fbeam,
        "umu0":  torch.ones(ncol) * umu0,
        "albedo":torch.zeros(nwave,ncol)
    }

    for w0, g in [(0.5, 0.0), (0.5, 0.5), (0.9, 0.5)]:
        prop[:,:,:,1] = w0  # single-scattering albedo
        prop[:,:,:,2] = g   # asymmetry factor

        result = toon(prop, **bc)

        toon_out = {
            "min_up": float(result[0,0,:,0].min()),
            "min_dn": float(result[0,0,:,1].min()),
            "up_toa": float(result[0,0,-1,0]),
            "dn_surf": float(result[0,0,0,1])
        }

        assert toon_out["min_up"] >= -1e-10, (
            f"Negative upward flux for w0={w0}, g={g}: {toon_out['min_up']}"
        )
        assert toon_out["min_dn"] >= -1e-10, (
            f"Negative downward flux for w0={w0}, g={g}: {toon_out['min_dn']}"
        )
        assert toon_out["up_toa"] <= incident + 1e-6, (
            f"TOA upward flux exceeds incident for w0={w0}, g={g}"
        )
        assert toon_out["dn_surf"] <= incident + 1e-6, (
            f"Surface downward flux exceeds incident for w0={w0}, g={g}"
        )

def test_toon_sw_vs_disort():
    """Toon and DISORT surface downward fluxes must agree within a factor of 3.

    For optically moderate atmospheres, both solvers give qualitatively
    consistent surface downward fluxes despite the two-stream approximation.
    """
    nwave = 1
    ncol = 1
    nlyr = 10
    nprop = 3
    nstr = 4
    tau = 0.1
    fbeam = 1.0
    umu0 = 0.5
    wave_lo = [200.0, 500.0, 1000.0]
    wave_hi = [500.0, 1000.0, 2000.0]

    opt = pyharp.ToonMcKay89Options()
    opt.wave_lower(wave_lo)
    opt.wave_upper(wave_hi)
    toon = pyharp.ToonMcKay89(opt)

    dop = pydisort.DisortOptions()
    dop.upward(True)
    dop.flags("lamber,quiet,onlyfl")
    dop.wave_lower(wave_lo)
    dop.wave_upper(wave_hi)
    pyharp.disort_config(dop, nstr, nlyr, ncol, nwave)
    disort = pydisort.Disort(dop)

    # accommodate both Toon and DISORT prop array shapes with max(nprop, 2+nstr)
    prop = torch.zeros(nwave,ncol,nlyr,max(nprop,2+nstr))
    prop[:,:,:,0] = tau  # optical depth

    bc = {
        "fbeam": torch.ones(nwave,ncol) * fbeam,
        "umu0":  torch.ones(ncol) * umu0,
        "albedo":torch.zeros(nwave,ncol)
    }

    for w0, g in [(0.1, 0.5), (0.5, 0.5), (0.9, 0.5), (0.5, 0.1), (0.5, 0.9)]:
        prop[:,:,:,1] = w0  # single-scattering albedo
        prop[:,:,:,2] = g   # asymmetry factor

        result = toon(prop, **bc)

        dn_toon = float(result[0,0,0,1])

        # for disort, the scattering coefficients are stored in prop[:,:,:,2+l] for l=0..nstr-1
        for l in range(nstr):
            prop[:,:,:,2+l] = g**(l+1)

        result = disort(prop, **bc)

        dn_disort = float(result[0,0,0,1])

        ratio = dn_toon / (dn_disort + 1e-30)
        print(f"w0={w0}, g={g}: Toon dn_surf={dn_toon:.4f}, "
              f"DISORT dn_surf={dn_disort:.4f}, ratio={ratio:.3f}")
        assert 0.8 < ratio < 1.2, (
            f"Surface dn flux ratio outside [0.8, 1.2] for w0={w0}, g={g}: "
            f"toon={dn_toon:.4f}, disort={dn_disort:.4f}, ratio={ratio:.3f}"
        )

def test_toon_lw_isothermal():
    """Toon and DISORT longwave fluxes must agree for an isothermal atmosphere.

    For a uniform temperature profile and moderate optical depth, the upward
    flux at TOA from Toon must be within 20% of the DISORT reference.
    """
    nwave = 3
    ncol = 1
    nlyr = 10
    nprop = 3
    nstr = 4
    tau = 0.3
    temp_K = 300.0
    wave_lo = [500.0, 1000.0, 1500.0]
    wave_hi = [1000.0, 1500.0, 2000.0]

    opt = pyharp.ToonMcKay89Options()
    opt.wave_lower(wave_lo)
    opt.wave_upper(wave_hi)
    opt.flags("planck")
    toon = pyharp.ToonMcKay89(opt)

    dop = pydisort.DisortOptions()
    dop.upward(True)
    dop.flags("lamber,quiet,onlyfl,planck")
    dop.wave_lower(wave_lo)
    dop.wave_upper(wave_hi)
    pyharp.disort_config(dop, nstr, nlyr, ncol, nwave)
    disort = pydisort.Disort(dop)

    # accommodate both Toon and DISORT prop array shapes with max(nprop, 2+nstr)
    prop = torch.zeros(nwave,ncol,nlyr,max(nprop,2+nstr))
    prop[:,:,:,0] = tau  # optical depth

    bc = {
        "albedo": torch.zeros(nwave,ncol),
        "temis":  torch.zeros(nwave,ncol),
        "btemp":  torch.ones(ncol) * temp_K,
        "ttemp":  torch.zeros(ncol) * temp_K
    }

    temf = torch.ones(ncol,nlyr+1) * temp_K

    result = toon(prop, temf=temf, **bc)
    toon_out = {
        "up_toa": result[:,:,-1,0].tolist()  # upward flux at TOA
    }

    result = disort(prop, temf=temf, **bc)
    disort_out = {
        "up_toa": result[:,:,-1,0].tolist()  # upward flux at TOA
    }

    for iw in range(nwave):
        up_t = toon_out["up_toa"][iw][0]
        up_d = disort_out["up_toa"][iw][0]
        print(f"Band {iw}: Toon up_TOA={up_t:.4f}, DISORT up_TOA={up_d:.4f}")
        assert up_t > 0, f"Toon LW upward TOA flux non-positive for band {iw}"
        assert up_d > 0, f"DISORT LW upward TOA flux non-positive for band {iw}"
        rel_diff = abs(up_t - up_d) / (abs(up_d) + 1e-30)
        assert rel_diff < 0.20, (
            f"Toon/DISORT LW TOA flux differ >20% for band {iw}: "
            f"toon={up_t:.4f}, disort={up_d:.4f}, rel_diff={rel_diff:.3f}"
        )

def test_toon_lw_isothermal_profile_matches_disort():
    """The `planck` flag should gate thermal emission and match DISORT aloft.

    Passing `temf` without the `planck` flag should keep Toon on the
    shortwave-only path. With `planck` enabled, the emitted upward longwave
    profile should closely match the DISORT reference for an isothermal column.
    """
    nwave = 1
    ncol = 1
    nlyr = 10
    nprop = 3
    nstr = 4
    tau = 0.3
    temp_K = 300.0
    wave_lo = [500.0]
    wave_hi = [1000.0]

    sw_opt = pyharp.ToonMcKay89Options()
    sw_opt.wave_lower(wave_lo)
    sw_opt.wave_upper(wave_hi)
    sw_toon = pyharp.ToonMcKay89(sw_opt)

    lw_opt = pyharp.ToonMcKay89Options()
    lw_opt.wave_lower(wave_lo)
    lw_opt.wave_upper(wave_hi)
    lw_opt.flags("planck")
    toon = pyharp.ToonMcKay89(lw_opt)

    dop = pydisort.DisortOptions()
    dop.upward(True)
    dop.flags("lamber,quiet,onlyfl,planck")
    dop.wave_lower(wave_lo)
    dop.wave_upper(wave_hi)
    pyharp.disort_config(dop, nstr, nlyr, ncol, nwave)
    disort = pydisort.Disort(dop)

    prop = torch.zeros(nwave, ncol, nlyr, max(nprop, 2 + nstr))
    prop[:, :, :, 0] = tau

    bc = {
        "albedo": torch.zeros(nwave, ncol),
        "temis": torch.ones(nwave, ncol),
        "btemp": torch.ones(ncol) * temp_K,
        "ttemp": torch.ones(ncol) * temp_K,
    }
    temf = torch.ones(ncol, nlyr + 1) * temp_K

    sw_result = sw_toon(prop, temf=temf, **bc)
    toon_result = toon(prop, temf=temf, **bc)
    disort_result = disort(prop, temf=temf, **bc)

    assert torch.allclose(sw_result, torch.zeros_like(sw_result))

    toon_up = toon_result[0, 0, :, 0]
    disort_up = disort_result[0, 0, :, 0]

    toon_scale = float(torch.mean(toon_up))
    disort_scale = float(torch.mean(disort_up))

    assert torch.max(torch.abs(toon_up - torch.mean(toon_up))) / toon_scale < 1e-2, (
        f"Toon isothermal LW upward profile is not flat enough: "
        f"{float(torch.max(torch.abs(toon_up - torch.mean(toon_up))) / toon_scale):.3e}"
    )
    assert torch.max(torch.abs(disort_up - torch.mean(disort_up))) / disort_scale < 1e-2, (
        f"DISORT isothermal LW upward profile is not flat enough: "
        f"{float(torch.max(torch.abs(disort_up - torch.mean(disort_up))) / disort_scale):.3e}"
    )

    # Toon's band Planck function uses the exact SI constants, so its flux is
    # pi * int B_nu dnu; DISORT's (c_planck_func2 of pydisort, C2 = 1.438786,
    # sigma = 5.67032e-8) is 7.8e-6 below it in this band.
    mp.mp.dps = 30
    h, c, k = mp.mpf("6.62607015e-34"), mp.mpf(299792458), mp.mpf("1.380649e-23")

    def planck(nu):  # B_nu per cm^-1, nu in cm^-1
        return 2 * h * c**2 * (100 * nu)**3 * 100 / mp.expm1(h * c * 100 * nu / (k * temp_K))

    exact = float(mp.pi * mp.quad(planck, [wave_lo[0], wave_hi[0]]))
    assert torch.max(torch.abs(toon_up - exact)) / exact < 1.5e-6, (
        f"Toon isothermal LW upward profile differs from pi * int B dnu: "
        f"{float(torch.max(torch.abs(toon_up - exact)) / exact):.3e}"
    )

    up_profile_scale = max(float(torch.max(torch.abs(disort_up))), 1e-30)
    assert torch.max(torch.abs(toon_up - disort_up)) / up_profile_scale < 1.5e-5, (
        f"Toon/DISORT isothermal LW upward profile mismatch too large: "
        f"{float(torch.max(torch.abs(toon_up - disort_up)) / up_profile_scale):.3e}"
    )

def test_toon_lw_isothermal_scattering():
    """Toon and DISORT longwave fluxes must agree for an isothermal atmosphere.

    For a uniform temperature profile and moderate optical depth, the upward
    flux at TOA from Toon must be within 20% of the DISORT reference.
    """
    nwave = 3
    ncol = 1
    nlyr = 10
    nprop = 3
    nstr = 4
    tau = 0.3
    temp_K = 300.0
    wave_lo = [500.0, 1000.0, 1500.0]
    wave_hi = [1000.0, 1500.0, 2000.0]

    opt = pyharp.ToonMcKay89Options()
    opt.wave_lower(wave_lo)
    opt.wave_upper(wave_hi)
    opt.flags("planck")
    toon = pyharp.ToonMcKay89(opt)

    dop = pydisort.DisortOptions()
    dop.upward(True)
    dop.flags("lamber,quiet,onlyfl,planck")
    dop.wave_lower(wave_lo)
    dop.wave_upper(wave_hi)
    pyharp.disort_config(dop, nstr, nlyr, ncol, nwave)
    disort = pydisort.Disort(dop)

    # accommodate both Toon and DISORT prop array shapes with max(nprop, 2+nstr)
    prop = torch.zeros(nwave,ncol,nlyr,max(nprop,2+nstr))
    prop[:,:,:,0] = tau  # optical depth

    bc = {
        "albedo": torch.zeros(nwave,ncol),
        "temis":  torch.zeros(nwave,ncol),
        "btemp":  torch.ones(ncol) * temp_K,
        "ttemp":  torch.zeros(ncol) * temp_K
    }

    temf = torch.ones(ncol,nlyr+1) * temp_K

    for w0, g in [(0.1, 0.5), (0.5, 0.5), (0.9, 0.5), (0.5, 0.1), (0.5, 0.9)]:
        prop[:,:,:,1] = w0  # single-scattering albedo
        prop[:,:,:,2] = g   # asymmetry factor

        result = toon(prop, temf=temf, **bc)
        toon_out = {
            "up_toa": result[:,:,-1,0].tolist()  # upward flux at TOA
        }

        for l in range(nstr):
            prop[:,:,:,2+l] = g**(l+1)

        result = disort(prop, temf=temf, **bc)
        disort_out = {
            "up_toa": result[:,:,-1,0].tolist()  # upward flux at TOA
        }

        print(f"Scattering case w0={w0}, g={g}:")

        for iw in range(nwave):
            up_t = toon_out["up_toa"][iw][0]
            up_d = disort_out["up_toa"][iw][0]
            print(f"Band {iw}: Toon up_TOA={up_t:.4f}, DISORT up_TOA={up_d:.4f}")
            assert up_t > 0, f"Toon LW upward TOA flux non-positive for band {iw}"
            assert up_d > 0, f"DISORT LW upward TOA flux non-positive for band {iw}"
            rel_diff = abs(up_t - up_d) / (abs(up_d) + 1e-30)
            assert rel_diff < 0.20, (
                f"Toon/DISORT LW TOA flux differ >20% for band {iw}: "
                f"toon={up_t:.4f}, disort={up_d:.4f}, rel_diff={rel_diff:.3f}"
            )


def _exact_lw_flux(dtau, B, nmu=64):
    """Absorption-only formal solution (independent reference): B linear in tau within each layer, Gauss-Legendre in mu.
    Level 0 = bottom, I_up(bottom) = B[0] (isotropic, at the base of a deep column), no TOA downwelling.
    Returns (up, down) fluxes per level in the units of pi * B."""
    import numpy as np
    x, w = np.polynomial.legendre.leggauss(nmu)
    mu, w = 0.5 * (x + 1.0), 0.5 * w
    n = len(dtau)
    s = (B[1:] - B[:-1]) / dtau  # dB/dtau going up through layer k
    up, dn = np.zeros(n + 1), np.zeros(n + 1)
    for m, wm in zip(mu, w):
        e = np.exp(-dtau / m)
        Id, Iu = np.zeros(n + 1), np.zeros(n + 1)
        for k in range(n - 1, -1, -1):
            Id[k] = Id[k + 1] * e[k] + B[k] - B[k + 1] * e[k] + s[k] * m * (1 - e[k])
        Iu[0] = B[0]
        for k in range(n):
            Iu[k + 1] = Iu[k] * e[k] + B[k + 1] - B[k] * e[k] - s[k] * m * (1 - e[k])
        up += 2 * math.pi * wm * m * Iu
        dn += 2 * math.pi * wm * m * Id
    return up, dn


def test_toon_lw_deep_bottom_matches_continued_column():
    """Gas-giant lower boundary (hard_surface off) on a lapse-rate column.

    The column is cut at an optically thick bottom where T still rises with p. The
    truth is the SAME column continued downward (same tau(p), T(p) laws) until it is
    opaque, solved exactly; the cut column's bottom net flux must match it. The
    diffusion source B_b + mu dB/dtau with the bottom-LAYER mean gradient is up to
    20 % high here (tau ~ p^2 on 30 layers); the gradient at the bottom LEVEL is
    within 3.5 %. An isotropic B(T_b) bottom (DISORT lamber) would give ~0.55x.
    Interior fluxes do not depend on the lower boundary.
    """
    import numpy as np

    wlo, whi = 200.0, 400.0
    opt = pyharp.ToonMcKay89Options()
    opt.wave_lower([wlo])
    opt.wave_upper([whi])
    opt.flags("planck")
    toon = pyharp.ToonMcKay89(opt)

    def planck(T):  # band radiance, the same function Toon uses
        return pyharp.bbflux_wavenumber(wlo, whi, torch.tensor(T)).numpy().reshape(-1)

    def column(tau_b, nexp, kappa, nlay, extend=0.0):
        p = np.logspace(0.0, -3.0, nlay + 1)  # p / p_bottom, bottom -> top
        if extend:
            pe = (extend / tau_b) ** (1.0 / nexp)
            d = 3.0 / nlay
            k = int(math.ceil(math.log10(pe) / d))
            p = np.concatenate([10 ** (d * np.arange(k, 0, -1)), p])
        tau = tau_b * p**nexp
        return tau[:-1] - tau[1:], 140.0 * p**kappa, len(p) - nlay - 1

    for tau_b, nexp, kappa in [(100.0, 2, 0.1), (10.0, 2, 0.3), (100.0, 1, 0.1)]:
        nlay = 30
        dtau, tlev, _ = column(tau_b, nexp, kappa, nlay)
        prop = torch.zeros(1, 1, nlay, 3)
        prop[0, 0, :, 0] = torch.tensor(dtau)
        bc = {
            "albedo": torch.zeros(1, 1),
            "temis": torch.ones(1, 1),
            "btemp": torch.tensor([tlev[0]]),
            "ttemp": torch.zeros(1),
        }
        flx = toon(prop, temf=torch.tensor(tlev)[None, :], **bc)[0, 0]
        net = (flx[:, 0] - flx[:, 1]).numpy()

        dt2, t2, ib = column(tau_b, nexp, kappa, nlay, extend=50 * tau_b + 50)
        up, dn = _exact_lw_flux(dt2, planck(t2))
        ref = (up - dn)[ib:]

        r_bot = net[0] / ref[0]
        mid = nlay // 2
        r_mid = net[mid] / ref[mid]
        print(f"  tau_b={tau_b:g} tau~p^{nexp} kappa={kappa}: bottom net/truth={r_bot:.4f}, mid={r_mid:.6f}")
        assert abs(r_bot - 1.0) < 0.05, (
            f"Toon LW bottom net flux off the continued column by {r_bot - 1:+.3f} "
            f"(tau_b={tau_b}, tau~p^{nexp}, kappa={kappa})"
        )
        assert abs(r_mid - 1.0) < 2e-3, f"Toon LW interior net flux off by {r_mid - 1:+.2e}"


if __name__ == "__main__":
    print("test_toon_sw_pure_absorption")
    test_toon_sw_pure_absorption()
    print("PASSED")

    print("test_toon_sw_scattering")
    test_toon_sw_scattering()
    print("PASSED")

    print("test_toon_sw_vs_disort")
    test_toon_sw_vs_disort()
    print("PASSED")

    print("test_toon_lw_isothermal")
    test_toon_lw_isothermal()
    print("PASSED")

    print("test_toon_lw_isothermal_profile_matches_disort")
    test_toon_lw_isothermal_profile_matches_disort()
    print("PASSED")

    print("test_toon_lw_isothermal_scattering")
    test_toon_lw_isothermal_scattering()
    print("PASSED")

    print("test_toon_lw_deep_bottom_matches_continued_column")
    test_toon_lw_deep_bottom_matches_continued_column()
    print("PASSED")
