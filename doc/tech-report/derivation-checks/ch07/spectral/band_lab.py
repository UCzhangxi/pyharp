"""Build RadiationBand configurations for the spectral-integration checks.

Every band is grey (a JIT opacity that returns a constant extinction
coefficient in 1/m, optionally with a prescribed spectral shape), so the
band flux of an isothermal, optically thick column has the closed form
F_up(TOA) = pi * int_band B_nu(T) dnu, independent of the solver's closure.
"""

import os
import numpy as np
import torch
import yaml

import pyharp
from pyharp import RadiationOptions, RadiationBand

torch.set_default_dtype(torch.float64)
torch.set_num_threads(1)


class GreyOpacity(torch.nn.Module):
    """Constant extinction coefficient [1/m], no scattering."""

    def __init__(self, nwave: int, kext: float):
        super().__init__()
        self.nwave = nwave
        self.kext = kext

    def forward(self, conc: torch.Tensor, temp: torch.Tensor) -> torch.Tensor:
        ncol, nlyr = conc.shape[0], conc.shape[1]
        return self.kext * torch.ones(
            (self.nwave, ncol, nlyr, 1), dtype=torch.float64
        )


class LineOpacity(torch.nn.Module):
    """Lorentzian line in wavenumber: k(nu) = kc + ka*hw^2/((nu-nu0)^2+hw^2)."""

    def __init__(self, kc: float, ka: float, nu0: float, hw: float):
        super().__init__()
        self.kc = kc
        self.ka = ka
        self.nu0 = nu0
        self.hw = hw

    def forward(self, conc: torch.Tensor, wavenumber: torch.Tensor,
                temp: torch.Tensor) -> torch.Tensor:
        ncol, nlyr = conc.shape[0], conc.shape[1]
        k = self.kc + self.ka * self.hw ** 2 / (
            (wavenumber - self.nu0) ** 2 + self.hw ** 2
        )
        return k.view(-1, 1, 1, 1) * torch.ones(
            (k.numel(), ncol, nlyr, 1), dtype=torch.float64
        )


def compile_grey(path, nwave, kext):
    pyharp.compile(GreyOpacity(nwave, kext), path)
    return path


def compile_line(path, kc, ka, nu0, hw):
    pyharp.compile(LineOpacity(kc, ka, nu0, hw), path)
    return path


def make_band(
    name,
    wmin,
    wmax,
    nwave,
    nlyr,
    solver,
    opacity_file,
    jit_kwargs=("temp",),
    flags="planck",
    nstr=4,
    tag="band",
    workdir=".",
):
    """Create RadiationBandOptions through the public YAML entry point."""
    cfg = {
        "species": [{"name": "X", "composition": {"H": 1}}],
        "geometry": {"cells": {"nx1": nlyr}},
        "opacities": {
            "grey": {
                "type": "jit",
                "data": [opacity_file],
                "jit_kwargs": list(jit_kwargs),
            }
        },
        "bands": [
            {
                "name": name,
                "range": [float(wmin), float(wmax)],
                "opacities": ["grey"],
                "solver": solver,
                "flags": flags,
                "nwave": int(nwave),
                "nstr": int(nstr),
            }
        ],
    }
    fn = os.path.join(workdir, f"{tag}.yaml")
    with open(fn, "w") as f:
        yaml.safe_dump(cfg, f)
    rad_op = RadiationOptions.from_yaml(fn)
    bo = rad_op.bands()[0]
    if solver == "disort":
        # RadiationBandOptionsImpl::from_yaml -> create_disort_config never sets
        # ds().nphase; it is left uninitialised. Pin it so the runs below are
        # reproducible (see the note in the report).
        bo.disort().ds().nphase = int(nstr)
    return bo


def isothermal_column(nlyr, temp_k, dz_m, ncol=1):
    conc = torch.ones((ncol, nlyr, 1), dtype=torch.float64)
    dz = dz_m * torch.ones((nlyr,), dtype=torch.float64)
    atm = {
        "temp": temp_k * torch.ones((ncol, nlyr), dtype=torch.float64),
        "pres": 1.0e4 * torch.ones((ncol, nlyr), dtype=torch.float64),
        "tempf": temp_k * torch.ones((ncol, nlyr + 1), dtype=torch.float64),
    }
    return conc, dz, atm


def run_band(band_opt, conc, dz, atm, albedo=0.0, btemp=None, ttemp=0.0,
             temis=0.0):
    nwave = band_opt.nwave()
    ncol = conc.shape[0]
    name = band_opt.name()
    bc = {
        f"{name}/albedo": albedo * torch.ones((nwave, ncol), dtype=torch.float64),
        f"{name}/temis": temis * torch.ones((nwave, ncol), dtype=torch.float64),
        "ttemp": ttemp * torch.ones((ncol,), dtype=torch.float64),
    }
    if btemp is None:
        btemp = float(atm["tempf"][0, 0])
    bc["btemp"] = btemp * torch.ones((ncol,), dtype=torch.float64)
    band = RadiationBand(band_opt)
    flx = band.forward(conc, dz, bc, dict(atm))
    return flx


def toa_up(flx):
    """Upward flux at the top level [W/m^2] for column 0."""
    return float(flx[0, -1, 0])


def sfc_dn(flx):
    return float(flx[0, 0, 1])
