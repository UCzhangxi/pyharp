"""ch09 figure: the support matrix, solver x operation, for the two pydisort versions.

Each cell is pass (the measured difference within its tolerance), fail (a candidate defect the text records),
unsupported (the call raises) or not applicable. Data: src/pyharp_report/ch09/data/cells_pydisort_*.json, written
by derivation-checks/check_ch09_batch_device.py (--data) at the code pin of code_pin.yml.
"""
from matplotlib.patches import Rectangle

from pyharp_report import figstyle as fs
from pyharp_report.ch09.figures._data import cells

SOLVERS = [("Toon SW", "Toon SW"), ("Toon LW", "Toon LW"), ("DISORT SW", "DISORT SW"), ("DISORT LW", "DISORT LW"),
           ("RadiationBand DISORT", "band, DISORT")]
OPS = [("batch f64", "batch\nf64"), ("CUDA f64", "CUDA\nf64"), ("batch f32", "batch\nf32"), ("CUDA f32", "CUDA\nf32")]
STYLE = {"pass": (fs.GREEN, "pass"), "fail": (fs.VERMILLION, "fail"), "unsupported": (fs.GHOST_FILL, "none"),
         "-": (fs.WHITE, "n/a")}


def make_fig():
    data = cells()
    vers = list(data)
    fig, ax = fs.new_figure("double", 2.6)
    fs.cartoon(ax)
    ncol = len(OPS) * len(vers)
    for j, (v) in enumerate(vers):
        x0 = j * (len(OPS) + 0.4)
        ax.text(x0 + len(OPS) / 2, len(SOLVERS) + 1.25, f"pydisort {v}", ha="center", va="bottom",
                fontsize=fs.LABEL_PT)
        for k, (op, lab) in enumerate(OPS):
            ax.text(x0 + k + 0.5, len(SOLVERS) + 0.05, lab, ha="center", va="bottom", fontsize=fs.SMALL_PT)
            for i, (s, _) in enumerate(SOLVERS):
                st = data[v].get(f"{s}|{op}", ["-", ""])[0]
                col, word = STYLE.get(st, STYLE["-"])
                y = len(SOLVERS) - 1 - i
                ax.add_patch(Rectangle((x0 + k, y), 1, 1, fc=col, ec=fs.BLACK, lw=0.6,
                                       hatch="//" if st == "unsupported" else None))
                ax.text(x0 + k + 0.5, y + 0.5, word, ha="center", va="center", fontsize=fs.SMALL_PT,
                        color=fs.WHITE if st in ("pass", "fail") else fs.BLACK,
                        bbox=None if st in ("pass", "fail", "-") else dict(boxstyle="round,pad=0.15", fc=fs.WHITE,
                                                                          ec="none"))
    for i, (_, lab) in enumerate(SOLVERS):
        ax.text(-0.15, len(SOLVERS) - 1 - i + 0.5, lab, ha="right", va="center", fontsize=fs.SMALL_PT)
    ax.set_xlim(-2.4, ncol + 0.4 * (len(vers) - 1) + 0.1)
    ax.set_ylim(-0.1, len(SOLVERS) + 1.9)
    return fig
