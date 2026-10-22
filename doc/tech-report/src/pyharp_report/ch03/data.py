"""Readers of the committed outputs of the chapter 3 checks (derivation-checks/ch03_*.out).

The checks run against pydisort 1.7.1 (the pin of code_pin.yml) and 1.8.13; the figures read the 1.7.1 outputs.
Every reader parses the fixed-width table the check prints; see the check script for its columns.
"""
from pathlib import Path

CHECKS = Path(__file__).resolve().parents[3] / "derivation-checks"
PIN_VERSION = "1.7.1"


def _lines(check):
    return (CHECKS / f"ch03_{check}.pydisort-{PIN_VERSION}.out").read_text().splitlines()


def e3_rows():
    """[(nstr, tau, rel_up, rel_dn)] from ch03_e3_slab"""
    rows = []
    for line in _lines("e3_slab"):
        f = line.split()
        if len(f) == 8 and f[0].isdigit():
            rows.append((int(f[0]), float(f[1]), float(f[4]), float(f[7])))
    return rows


def delta_m_rows():
    """[(phase, tau, nstr, R_on, R_off, T_on, T_off)] relative errors from ch03_delta_m"""
    rows = []
    for line in _lines("delta_m"):
        f = line.split()
        if len(f) == 7 and f[0] in ("henyey-greenstein", "cloud-garcia-siewert"):
            rows.append((f[0], float(f[1]), int(f[2])) + tuple(float(x) for x in f[3:]))
    return rows


def intensity_correction_rows():
    """[(nstr, aureole_off, aureole_on, outside_off, outside_on, top_off, top_on)] from ch03_intensity_correction"""
    rows = []
    for line in _lines("intensity_correction"):
        f = line.split()
        if len(f) == 11 and f[0].isdigit():
            rows.append((int(f[0]),) + tuple(float(x) for x in f[1:7]))
    return rows
