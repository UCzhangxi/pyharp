"""Readers of the committed outputs of the chapter 8 checks (derivation-checks/ch08_*.out).

The checks run against pydisort 1.7.1 (the pin of code_pin.yml) and 1.8.13; the figures read the 1.7.1 outputs.
Each reader parses the tagged lines the check prints; see the check script for their columns.
"""
from pathlib import Path

CHECKS = Path(__file__).resolve().parents[3] / "derivation-checks"
PIN_VERSION = "1.7.1"


def _lines(check):
    return (CHECKS / f"ch08_{check}.pydisort-{PIN_VERSION}.out").read_text().splitlines()


def spherical_factors():
    """{geometry: [(level, code factor, documented factor)]} from ch08_spherical (lines 'level <geometry> q code x
    documented y')"""
    out = {}
    for line in _lines("spherical"):
        f = line.split()
        if len(f) == 7 and f[0] == "level":
            out.setdefault(f[1], []).append((int(f[2]), float(f[4]), float(f[6])))
    return out


def stepper_convergence():
    """{scheme: [(nsteps, dt [s], max |T - T_ref| [K])]} from ch08_stepper (lines 'conv <scheme> n dt err')"""
    out = {}
    for line in _lines("stepper"):
        f = line.split()
        if len(f) == 5 and f[0] == "conv":
            out.setdefault(f[1], []).append((int(f[2]), float(f[3]), float(f[4])))
    return out
