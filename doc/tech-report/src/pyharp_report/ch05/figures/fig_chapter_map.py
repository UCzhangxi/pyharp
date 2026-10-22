"""ch05 figure: how the four sections of the chapter depend on each other (a cartoon; no data)."""
from matplotlib.patches import FancyArrowPatch

from pyharp_report import figstyle as fs

BOXES = {"ref": (0.0, 1.2, "converged DISORT\n(nstr = N_ref)"),
         "ana": (0.0, 0.0, "analytic cases\nand energy closure"),
         "toon": (3.4, 1.2, "Toon89 error:\nnumerical + approximation"),
         "cost": (3.4, 0.0, "cost per column\nof both solvers")}


def make_fig():
    fig, ax = fs.new_figure("double", 1.7)
    fs.cartoon(ax)
    w, h = 2.4, 0.75
    for x, y, lab in BOXES.values():
        fs.cell(ax, x, y, w, h, fill=True)
        ax.text(x + w / 2, y + h / 2, lab, ha="center", va="center", fontsize=fs.SMALL_PT)
    arrows = [((2.4, 1.575), (3.4, 1.575), "reference for"), ((1.2, 0.75), (1.2, 1.2), "checks"),
              ((4.6, 1.2), (4.6, 0.75), "price of")]
    for p0, p1, lab in arrows:
        ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=8, lw=1.0, color=fs.BLACK))
        ax.text(0.5 * (p0[0] + p1[0]) + (0.08 if p0[0] == p1[0] else 0), 0.5 * (p0[1] + p1[1]) + 0.08, lab,
                ha="left" if p0[0] == p1[0] else "center", va="bottom", fontsize=fs.SMALL_PT)
    ax.set_xlim(-0.1, 5.9)
    ax.set_ylim(-0.1, 2.05)
    return fig
