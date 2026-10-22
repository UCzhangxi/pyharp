"""Data flow of one DISORT band call: pyharp's bottom-to-top arrays, pydisort's reversal, cdisort, and back.

A cartoon (no data) for nlyr = 4. The array orders and the two reversals are code facts of pyharp
(RadiationBandImpl::forward, create_disort_config) and pydisort (disort_impl) at the pins of code_pin.yml, cited
in the chapter text.
"""
from matplotlib.patches import FancyArrowPatch

from pyharp_report import figstyle as fs

H = 0.45   # cell height
Y0 = 0.45  # bottom of the column


def _column(ax, x, labels, title, note):
    ax.text(x + 0.5, Y0 + 4 * H + 0.2, title, ha="center", va="bottom", fontsize=fs.SMALL_PT)
    for k, lab in enumerate(labels):  # k = 0 is the bottom cell
        fs.cell(ax, x, Y0 + H * k, w=1.0, h=H, fill=True)
        ax.text(x + 0.5, Y0 + H * (k + 0.5), lab, ha="center", va="center", fontsize=fs.SMALL_PT)
    ax.text(x + 0.5, 0.15, note, ha="center", va="center", fontsize=fs.SMALL_PT)


def _arrow(ax, x0, x1, label):
    y = Y0 + 2 * H
    ax.add_patch(FancyArrowPatch((x0, y), (x1, y), arrowstyle="-|>", mutation_scale=9, lw=1.1, color=fs.ORANGE))
    ax.text(0.5 * (x0 + x1), y + 0.2, label, ha="center", va="bottom", fontsize=fs.SMALL_PT)


def make_fig():
    fig, ax = fs.new_figure("double", 2.3)
    fs.cartoon(ax)
    _column(ax, 0.0, ["0", "1", "2", "3"], "pyharp prop\nlayer index", "index 0 = bottom")
    _column(ax, 3.0, ["4", "3", "2", "1"], "cdisort arrays\nlayer number LC", "LC = 1 = top")
    ax.text(6.5, Y0 + 4 * H + 0.2, "pyharp flux\nlevel index", ha="center", va="bottom", fontsize=fs.SMALL_PT)
    for k in range(5):
        y = Y0 + H * k
        ax.plot([6.1, 6.9], [y, y], color=fs.BLACK, lw=0.8)
        fs.face_marker(ax, 6.5, y)
        ax.text(7.05, y, str(k), ha="left", va="center", fontsize=fs.SMALL_PT)
    ax.text(6.5, 0.15, "index 0 = surface", ha="center", va="center", fontsize=fs.SMALL_PT)
    _arrow(ax, 1.15, 2.85, "disort_impl\nreverses")
    _arrow(ax, 4.15, 5.85, "fluxes reversed\nback")
    ax.text(-0.35, Y0 + 2 * H, "up", ha="center", va="center", fontsize=fs.SMALL_PT, rotation=90)
    ax.add_patch(FancyArrowPatch((-0.2, Y0 + 2.6 * H), (-0.2, Y0 + 3.8 * H), arrowstyle="-|>", mutation_scale=8,
                                 lw=0.9, color=fs.BLACK))
    ax.set_xlim(-0.6, 7.6)
    ax.set_ylim(-0.05, Y0 + 4 * H + 0.75)
    return fig
