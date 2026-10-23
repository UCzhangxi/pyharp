"""Shared setup for the ch08 checks (Radiation API, configuration, coupling and the column model).

The checks run against an installed pyharp built from source at the code pin (code_pin.yml) and the pydisort wheel it
was built against; the interpreter that runs them must be the one pyharp was built in. Every check prints its versions
and the source commits first, then one `[Cn] PASS|FAIL <label>: <numbers>` line per claim and, for a behaviour the text
records as a CANDIDATE defect, one `[Pn] CANDIDATE reproduced|not reproduced <label>: <numbers>` line. The exit status
is the number of FAIL lines; a CANDIDATE line never fails the check.

pyharp indexes layers and levels from the BOTTOM (level 0 is the surface, level nlyr the top); flux channel 0 is the
upward flux and channel 1 the total downward flux.

Environment: PYHARP_WT and PYDISORT_SRC name the source trees (their commits are printed). The stepper check also
needs a C++17 compiler and ninja on PATH, and PYHARP_WT/build for the yaml-cpp and fmt headers of the pyharp build.
"""
import os
import subprocess
import sys

import numpy as np
import pydisort
import pyharp
import torch

F64 = torch.float64


def git_head(var):
    path = os.environ.get(var)
    if not path:
        return "unset"
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "not a git tree"


def header(extra=""):
    print(f"python {sys.version.split()[0]}, torch {torch.__version__}, numpy {np.__version__}, "
          f"pydisort {pydisort.__version__}{extra}")
    print(f"pyharp source {git_head('PYHARP_WT')}, pydisort source {git_head('PYDISORT_SRC')}")


class Slab(torch.nn.Module):
    """A grey opacity source: extinction k [1/m] per unit concentration, albedo ssa, Henyey-Greenstein moments g^l."""

    def __init__(self, k: float, ssa: float = 0.0, g: float = 0.0, nmom: int = 0):
        super().__init__()
        self.k = k
        self.ssa = ssa
        self.g = g
        self.nmom = nmom

    def forward(self, conc: torch.Tensor) -> torch.Tensor:
        out = torch.zeros((1, conc.shape[0], conc.shape[1], 2 + self.nmom), dtype=torch.float64)
        # fill_ keeps float64 under torch.jit.script
        out[..., 0].fill_(self.k)
        out[..., 1].fill_(self.ssa)
        for m in range(1, self.nmom + 1):
            out[..., 1 + m].fill_(self.g ** m)
        return out


def compile_slab(work, name, k, ssa=0.0, g=0.0, nmom=0):
    path = os.path.join(work, f"{name}.pt")
    pyharp.compile(Slab(k, ssa, g, nmom), path)
    return path


def write(work, name, text):
    path = os.path.join(work, name)
    with open(path, "w") as f:
        f.write(text)
    return path


def two_band_yaml(work, nlyr=4):
    """A shortwave DISORT band (scattering, beam) and a longwave DISORT band (absorbing, Planck), one species."""
    sw = compile_slab(work, "sw", 1e-3, 0.5, 0.5, 4)
    lw = compile_slab(work, "lw", 5e-4, 0.0, 0.0, 4)
    return write(work, "two_band.yaml", f"""species:
  - name: X
    composition: {{H: 2}}
geometry:
  cells:
    nx1: {nlyr}
opacities:
  osw: {{type: jit, species: [X], nmom: 4, data: [{sw}]}}
  olw: {{type: jit, species: [X], nmom: 4, data: [{lw}]}}
bands:
  - name: sw
    range: [10000.0, 20000.0]
    opacities: [osw]
    solver: disort
    nwave: 1
    nstr: 4
    flags: lamber,quiet,onlyfl
  - name: lw
    range: [500.0, 700.0]
    opacities: [olw]
    solver: disort
    nwave: 1
    nstr: 4
    flags: lamber,quiet,onlyfl,planck
""")


def set_unit_weights(rad_options):
    """Weight mode, one spectral point of weight 1 per band: the YAML parser reads neither weights nor a grid.
    A DISORT band also gets nphase = nstr, as pyharp.disort_config sets it: create_disort_config leaves nphase
    unset (ch08_config.py [P1]), and an unset nphase can stop cdisort while it allocates its phase array."""
    for b in rad_options.bands():
        b.weight([1.0] * b.nwave())
        if b.solver_name() == "disort":
            b.disort().ds().nphase = b.disort().ds().nstr
    return rad_options


def two_band_inputs(nlyr=4, albedo=0.3):
    conc = torch.ones((1, nlyr, 1), dtype=F64)
    dz = torch.full((nlyr,), 250.0, dtype=F64)
    bc = {"sw/umu0": torch.tensor([0.6], dtype=F64), "sw/fbeam": torch.tensor([[100.0]], dtype=F64),
          "sw/albedo": torch.tensor([[albedo]], dtype=F64), "lw/albedo": torch.tensor([[0.0]], dtype=F64),
          "btemp": torch.tensor([280.0], dtype=F64), "ttemp": torch.tensor([0.0], dtype=F64)}
    atm = {"tempf": torch.linspace(280.0, 240.0, nlyr + 1, dtype=F64).unsqueeze(0)}
    return conc, dz, bc, atm
