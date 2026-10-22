"""ch09 figure: how the three sections of the chapter depend on each other (a cartoon; no data)."""
from matplotlib.patches import FancyArrowPatch

from pyharp_report import figstyle as fs

BOXES = [(0.0, 0.0, "the build: CUDA kernels,\npydisort it links"),
         (5.2, 1.1, "Toon: batch and CUDA"), (5.2, -1.1, "DISORT on CUDA,\nby pydisort version")]


def make_fig():
    fig, ax = fs.new_figure("double", 1.9)
    fs.cartoon(ax)
    w, h = 2.7, 0.8
    for x, y, lab in BOXES:
        fs.cell(ax, x, y, w, h, fill=True)
        ax.text(x + w / 2, y + h / 2, lab, ha="center", va="center", fontsize=fs.SMALL_PT)
    for p1, lab in [((5.2, 1.5), "enables CUDA kernels"), ((5.2, -0.7), "selects pydisort")]:
        ax.add_patch(FancyArrowPatch((2.7, 0.4), p1, arrowstyle="-|>", mutation_scale=8, lw=1.0, color=fs.BLACK))
        ax.text(0.5 * (2.7 + p1[0]), 0.5 * (0.4 + p1[1]), lab, ha="center", va="center", fontsize=fs.SMALL_PT,
                bbox=dict(boxstyle="round,pad=0.15", fc=fs.WHITE, ec="none"))
    ax.set_xlim(-0.1, 8.0)
    ax.set_ylim(-1.2, 2.0)
    return fig
