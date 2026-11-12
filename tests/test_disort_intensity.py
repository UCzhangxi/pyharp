import math

import numpy as np
import pytest
import torch

import pyharp

NU = 1000.0  # cm^-1; wave_lower == wave_upper makes DISORT's Planck monochromatic
C1, C2 = 1.191042972e-8, 1.438776877  # W m^-2 sr^-1 (cm^-1)^-4, cm K (CODATA)


class Grey(torch.nn.Module):
    """Cross section 1 m^2/mol, so a layer's optical depth = conc * dz."""

    def __init__(self, ssa: float):
        super().__init__()
        self.ssa = ssa

    def forward(self, conc: torch.Tensor) -> torch.Tensor:
        ext = conc[..., 0].unsqueeze(0)
        return torch.stack([ext, torch.full_like(ext, self.ssa)], dim=-1)


def solve(tmp_path, dtau, ssa, nstr, umu, tempf, btemp):
    """dtau, tempf: top first; returns (TOA intensity at umu, TOA up flux)."""
    torch.jit.script(Grey(ssa)).save(str(tmp_path / "grey.pt"))
    (tmp_path / "grey.yaml").write_text(
        f"species:\n  - name: X\n    composition: {{H: 1}}\n"
        f"geometry:\n  cells:\n    nx1: {len(dtau)}\n"
        f"opacities:\n  grey:\n    type: jit\n    data: [{tmp_path / 'grey.pt'}]\n"
        f"bands:\n  - name: b\n    range: [{NU}, {NU}]\n    opacities: [grey]\n"
        f"    solver: disort\n    nwave: 1\n    nstr: {nstr}\n"
        f"    flags: lamber,quiet,planck,usrang,usrtau\n")
    band = pyharp.RadiationOptions.from_yaml(str(tmp_path / "grey.yaml")).bands()[0]
    band.wavenumber([NU]).set_wave_lower([NU]).set_wave_upper([NU])
    band.disort().user_mu(list(umu)).user_tau([0.0])
    rad = pyharp.RadiationBand(band)
    conc = torch.tensor(dtau[::-1].copy()).view(1, -1, 1)  # pyharp: bottom first
    temp = {"tempf": torch.tensor(tempf[::-1].copy()).view(1, -1)}
    bc = {"btemp": torch.tensor([btemp], dtype=torch.float64)}
    rad.forward(conc, torch.ones(len(dtau), dtype=torch.float64), bc, temp)
    return rad.buffer("intensity")[0, 0, 0, 0].numpy(), rad.buffer("spectrum")[0, 0, -1, 0].item()


def planck_temperature(b):
    return C2 * NU / np.log1p(C1 * NU**3 / b)


def test_linear_source_gives_linear_limb_law(tmp_path):
    # source a + b*tau over 0 <= tau <= T, black bottom at S(T):
    # I(0, mu) = a + b*mu*(1 - exp(-T/mu)) exactly
    a, b, T = 1.0e-3, 2.0e-3, 10.0
    tau = np.linspace(0.0, T, 41)
    umu = np.array([0.05, 0.1, 0.2, 0.35, 0.5, 0.7, 0.9, 1.0])
    tempf = planck_temperature(a + b * tau)
    inten, _ = solve(tmp_path, np.diff(tau), 0.0, 16, umu, tempf, tempf[-1])
    exact = a + b * umu * (1.0 - np.exp(-T / umu))
    # the ratio removes DISORT's own Planck constants (c1 = 1.1911e-8)
    np.testing.assert_allclose(inten / inten[-1], exact / exact[-1], rtol=1e-4)
    np.testing.assert_allclose(inten, exact, rtol=1e-4)


# H(mu) for conservative isotropic scattering, H_TABLE_SOURCE
H_TABLE = {}


def milne(tmp_path, nstr, umu):
    # conservative isotropic scattering over a black body at the bottom of a
    # thick (tau = 100) layer: the emergent law is H(mu)/H(1)
    dtau = np.full(50, 2.0)
    return solve(tmp_path, dtau, 1.0, nstr, umu, np.zeros(51), 1000.0)


def test_grey_scattering_follows_chandrasekhar_h_law(tmp_path):
    umu = np.array(sorted(H_TABLE))
    inten, _ = milne(tmp_path, 16, umu)
    h = np.array([H_TABLE[m] for m in umu])
    np.testing.assert_allclose(inten / inten[-1], h / h[-1], rtol=2e-4)


@pytest.mark.parametrize("ssa", [0.0, 1.0])
def test_intensity_integrates_to_disort_flux(tmp_path, ssa):
    # at DISORT's own (double-Gauss) quadrature angles the intensities sum to
    # its flux: F = 2 pi sum_i w_i mu_i I(mu_i)
    x, w = np.polynomial.legendre.leggauss(8)
    mu, w = (x + 1.0) / 2.0, w / 2.0
    if ssa == 0.0:
        tau = np.linspace(0.0, 10.0, 41)
        tempf = planck_temperature(1.0e-3 + 2.0e-3 * tau)
        inten, flux = solve(tmp_path, np.diff(tau), 0.0, 16, mu, tempf, tempf[-1])
    else:
        inten, flux = milne(tmp_path, 16, mu)
    assert 2.0 * math.pi * np.sum(w * mu * inten) == pytest.approx(flux, rel=1e-10)
