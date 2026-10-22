"""pydisort build/run matrix of tests/test_rayleigh.py (chapter 10, `_packaging.qmd`).

Reads src/pyharp_report/ch10/data/abi_matrix.csv, written by derivation-checks/ch10/abi_matrix.py --csv from the
committed outputs of derivation-checks/ch10/run_suite.sh on pyharp built from the pin of code_pin.yml.
"""
from pathlib import Path

from matplotlib.patches import Rectangle

from pyharp_report import figstyle as fs

DATA = Path(__file__).resolve().parent.parent / "data" / "abi_matrix.csv"


def make_fig():
    rows = [ln.split(",") for ln in DATA.read_text().splitlines()[1:]]
    versions = ["1.7.1", "1.8.13"]
    fig, ax = fs.new_figure("single", 2.2)
    fs.cartoon(ax)
    for built, run, runs, clean, aborted in rows:
        i, j = versions.index(built), versions.index(run)
        bad = int(aborted) > 0
        ax.add_patch(Rectangle((j, 1 - i), 1, 1, fc=fs.GHOST_FILL if bad else fs.CELL_FILL,
                               ec=fs.VERMILLION if bad else fs.BLACK, hatch="//" if bad else None, lw=1.0))
        text = f"{clean} clean\n{aborted} aborted" if bad else f"{clean} of {runs}\nclean"
        ax.text(j + 0.5, 1.5 - i, text, ha="center", va="center", fontsize=fs.SMALL_PT,
                bbox=dict(boxstyle="round,pad=0.15", fc=fs.WHITE, ec="none"))
    for k, v in enumerate(versions):
        ax.text(k + 0.5, 2.08, v, ha="center", va="bottom", fontsize=fs.SMALL_PT)
        ax.text(-0.06, 1.5 - k, v, ha="right", va="center", fontsize=fs.SMALL_PT)
    ax.text(1.0, 2.35, "pydisort at run time", ha="center", va="bottom", fontsize=fs.SMALL_PT)
    ax.text(-0.75, 1.0, "built against", ha="center", va="center", rotation=90, fontsize=fs.SMALL_PT)
    ax.set_xlim(-1.0, 2.1)
    ax.set_ylim(-0.1, 2.7)
    return fig
