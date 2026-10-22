"""ch09 figure: how far Toon89's batched and CUDA fluxes are from the per-column CPU fluxes.

For the shortwave and thermal kernels, float64 and float32: the normalised largest difference of one batched call
against single-column calls (CPU), and of CUDA against CPU, with the tolerances of check_ch09_batch_device.py.
Differences of exactly zero (bitwise-equal results) are drawn at the bottom of the axis. Data:
src/pyharp_report/ch09/data/cells_pydisort_1.7.1.json, written by derivation-checks/check_ch09_batch_device.py
(--data) at the code pin of code_pin.yml; the Toon cells do not depend on the pydisort version.
"""
import numpy as np

from pyharp_report import figstyle as fs
from pyharp_report.ch09.figures._data import cells

FLOOR = 1e-17


def make_fig():
    c = cells()["1.7.1"]
    keys = [("batch f64", "batch, float64"), ("CUDA f64", "CUDA, float64"), ("batch f32", "batch, float32"),
            ("CUDA f32", "CUDA, float32")]
    tols = [1e-14, 1e-12, 1e-6, 2.6e-5]
    x = np.arange(len(keys))
    fig, ax = fs.new_figure("double", 2.4)
    for off, solver, col, hatch in [(-0.18, "Toon SW", fs.ORANGE, None), (0.18, "Toon LW", fs.SKY, "//")]:
        vals = [max(float(c[f"{solver}|{k}"][1]), FLOOR) for k, _ in keys]
        ax.bar(x + off, vals, 0.36, color=col, hatch=hatch, label=solver.replace("Toon SW", "shortwave")
               .replace("Toon LW", "thermal"), bottom=FLOOR)
    for i, tl in enumerate(tols):
        ax.plot([i - 0.4, i + 0.4], [tl, tl], color=fs.BLACK, ls=":", lw=1.0,
                label="tolerance" if i == 0 else None)
    ax.set_yscale("log")
    ax.set_ylim(FLOOR, 1e-3)
    ax.set_xticks(x, [lab for _, lab in keys])
    ax.set_ylabel("normalised largest difference [-]")
    for i, (k, _) in enumerate(keys):
        for off, solver in [(-0.18, "Toon SW"), (0.18, "Toon LW")]:
            if float(c[f"{solver}|{k}"][1]) == 0.0:
                ax.text(i + off, 4 * FLOOR, "0", ha="center", va="bottom", fontsize=fs.SMALL_PT)
    ax.legend(loc="upper left")
    return fig
