from pathlib import Path

import numpy as np
import pytest

from pyharp.spectra.hitran_cia_utils import parse_cia_file

# HITRAN 2018 "alternate" H2-H2 sets (H2-H2_norm_2018.cia, H2-H2_eq_2018.cia): the 20-character chemical-symbol
# field holds "n-H2 -- n-H2" (or "eq-H2 -- eq-H2") instead of "H2-H2". The header lines below are verbatim
# from H2-H2_norm_2018.cia (blocks at 40 K and 51.662 K, first three rows each); the eq set differs only in
# the symbol and the comment.
HEADERS = {
    "n-H2": (
        "        n-H2 -- n-H2  0.250000 2400.0000   9600 40.000 2.606e-44 -.999         Para frac, fp=0.25 34",
        "        n-H2 -- n-H2  0.250000 2400.0000   9600 51.662 2.124e-44 -.999         Para frac, fp=0.25 34",
    ),
    "eq-H2": (
        "      eq-H2 -- eq-H2  0.250000 2400.0000   9600 40.000 3.683e-44 -.999                            34",
        "      eq-H2 -- eq-H2  0.250000 2400.0000   9600 51.662 2.124e-44 -.999                            34",
    ),
}
ROWS = (
    ("    0.2500  3.139E-50", "    0.5000  1.305E-49", "    0.7500  3.009E-49"),
    ("    0.2500  2.237E-50", "    0.5000  9.311E-50", "    0.7500  2.131E-49"),
)
TEMPERATURES = [40.0, 51.662]
WAVENUMBERS = [0.25, 0.5, 0.75]
CROSS_SECTIONS = ([3.139e-50, 1.305e-49, 3.009e-49], [2.237e-50, 9.311e-50, 2.131e-49])


def _write_alternate_file(tmp_path: Path, variant: str) -> Path:
    lines = []
    for header, rows in zip(HEADERS[variant], ROWS):
        lines.append(header)
        lines.extend(rows)
    path = tmp_path / f"H2-H2_{'norm' if variant == 'n-H2' else 'eq'}_2018.cia"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("variant", sorted(HEADERS))
def test_parse_hitran_2018_alternate_h2h2_header(tmp_path: Path, variant: str) -> None:
    path = _write_alternate_file(tmp_path, variant)

    dataset = parse_cia_file(path, "H2-H2")

    assert [block.temperature_k for block in dataset.blocks] == TEMPERATURES
    for block, expected in zip(dataset.blocks, CROSS_SECTIONS):
        assert np.allclose(block.wavenumber_cm1, WAVENUMBERS)
        assert np.allclose(block.binary_cross_section_cm5_molecule2, expected, rtol=0.0, atol=0.0)


def test_alternate_header_temperature_is_never_the_wavenumber_bound(tmp_path: Path) -> None:
    # Asking for the header's first token must not tag the blocks with another column (e.g. wmax = 2400):
    # either the label is rejected, or the temperatures are the header's temperature column.
    path = _write_alternate_file(tmp_path, "n-H2")

    try:
        dataset = parse_cia_file(path, "n-H2")
    except ValueError:
        return
    assert [block.temperature_k for block in dataset.blocks] == TEMPERATURES
