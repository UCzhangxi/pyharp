"""The one figure style of the pyharp Technical Report (STYLE.md sections 6.1, 6.2 and 10.4).

Every figure function styles through this module only; `tools/check_figstyle.py` counts styling done anywhere
else (another style module, an rcParams write, an inline font) per chapter and lets that count only shrink.

House style (STYLE 6.2), for new and ported figures:

    from pyharp_report import figstyle as fs
    fig, ax = fs.new_figure("double", 2.4)          # or "single", or nrows/ncols; a Figure not held by pyplot
    ax.text(x, y, "label", fontsize=fs.SMALL_PT)    # sizes and colours come from here, never as literals
    fs.panel_labels(axes); fs.cell(ax, ...); fs.cell_marker(ax, x, y); fs.wall_line(ax, p0, p1); ...

`new_figure` applies `RC`: DejaVu Sans, 9 pt labels (`LABEL_PT`), 8 pt ticks, legends and annotations (`SMALL_PT`,
also the floor `MIN_PT`), matplotlib's default (DejaVu Sans) mathtext, fonts embedded as TrueType, and the two
widths of STYLE 6.2, `DOUBLE` = 6.2 in (the PDF text width) and `SINGLE` = 3.05 in; `MONO` is the family for code
words and log lines. Colours are the Okabe-Ito palette with the meanings of STYLE 6.2.

This module also holds the names of an earlier figure API (`apply`, `cell_box`, `cell_value`, `face_value`,
`wall`, `slope_guide`, `save`, `DPI`, `GREY`); `apply()` sets 9 pt serif/STIX text. New figures call
`new_figure`, never `apply`. Helpers whose earlier name had another signature have a new name here
(`cell_marker`, `face_marker`, `wall_line`, `save_to`). A change of style is checked by the figure-output gate
(`tools/check_fig_output.py`).
"""
import logging
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

# Okabe-Ito, colour-blind safe; meanings fixed across the report (STYLE.md 6.2)
BLACK = "#000000"      # grid, walls, axes
ORANGE = "#E69F00"     # face quantities, fluxes
SKY = "#56B4E9"        # cell quantities
GREEN = "#009E73"      # the scheme being described (its added term)
YELLOW = "#F0E442"     # highlights
BLUE = "#0072B2"       # reference / exact
VERMILLION = "#D55E00"  # errors, defects, the term removed
PURPLE = "#CC79A7"     # ghosts, other blocks
GREY = "#999999"       # de-emphasised context (not a data colour)
CELL_FILL = "#EAF5FC"   # light blue: cell fill in cartoons
GHOST_FILL = "#F7E6EF"  # light reddish purple: ghost-cell fill in cartoons
WHITE = "#FFFFFF"
PALETTE = (BLACK, ORANGE, SKY, GREEN, BLUE, VERMILLION, PURPLE, CELL_FILL, GHOST_FILL, WHITE)

DOUBLE = 6.2  # in, the PDF text width (textwidth 448.13 pt: scrreprt, A4, DIV=12, 10 pt)
SINGLE = 3.05  # in, half of it less the gap between two figures side by side
WIDTHS = {"single": SINGLE, "double": DOUBLE}
ALLOWED_WIDTHS = (SINGLE, DOUBLE)  # STYLE 6.2; heights are free
DPI = 200

FONT = "DejaVu Sans"
MONO = "DejaVu Sans Mono"  # code words and log lines inside a figure
LABEL_PT = 9   # axis labels, titles, panel letters
SMALL_PT = 8   # ticks, legends, annotations
MIN_PT = 8     # no text smaller than this at print size (STYLE 6.2)

# fontTools reports the DejaVu files' zero timestamps when the PDF backend subsets them; in a Quarto cell that
# warning would be printed into the book
logging.getLogger("fontTools").setLevel(logging.ERROR)

#: the house settings (STYLE 6.2), applied by new_figure()
RC = {
    "font.family": FONT, "font.size": LABEL_PT, "axes.labelsize": LABEL_PT, "axes.titlesize": LABEL_PT,
    "xtick.labelsize": SMALL_PT, "ytick.labelsize": SMALL_PT, "legend.fontsize": SMALL_PT, "legend.frameon": False,
    "mathtext.fontset": "dejavusans", "text.usetex": False, "lines.linewidth": 1.4, "lines.markersize": 4.5,
    "axes.linewidth": 0.8, "hatch.color": BLACK, "svg.hashsalt": "pyharp-tech-report", "svg.fonttype": "path",
    "pdf.fonttype": 42, "ps.fonttype": 42, "path.simplify": False, "savefig.dpi": DPI,
    "axes.prop_cycle": matplotlib.cycler(color=[BLACK, ORANGE, SKY, GREEN, BLUE, VERMILLION, PURPLE]),
}


# ---- house API (STYLE 6.2) ---------------------------------------------------------------------------------------

def new_figure(width="double", height=2.4, nrows=1, ncols=1, **subplot_kw):
    """a constrained-layout Figure of a house width (STYLE 6.2) and its axes; not registered with pyplot, so a
    Quarto cell shows it once. `width` is "single", "double" or a width in inches."""
    matplotlib.rcParams.update(RC)
    fig = Figure(figsize=(WIDTHS.get(width, width), height), layout="constrained")
    return fig, fig.subplots(nrows, ncols, **subplot_kw)


def panel_labels(axes):
    """(a), (b), ... in the top left of each panel (STYLE 10.4)"""
    for n, ax in enumerate(getattr(axes, "flat", axes)):
        ax.text(0.0, 1.0, f"({'abcd'[n]})", transform=ax.transAxes, ha="left", va="bottom", fontsize=LABEL_PT,
                fontweight="bold")


def cartoon(ax):
    """a cartoon panel: no axes frame, equal aspect (STYLE 6.2)"""
    ax.set_axis_off()
    ax.set_aspect("equal")


def cell(ax, x, y, w=1.0, h=1.0, label=None, kind="fluid", fill=False):
    """a cell box; kind "fluid" or "ghost" (hatched // on the ghost fill)"""
    if kind == "ghost":
        style = dict(fc=GHOST_FILL, ec=PURPLE, hatch="//")
    else:
        style = dict(fc=CELL_FILL if fill else WHITE, ec=BLACK, hatch=None)
    box = ax.add_patch(Rectangle((x, y), w, h, lw=0.8, **style))
    if label is not None:
        ax.text(x + 0.5 * w, y + 0.5 * h, label, ha="center", va="center", fontsize=SMALL_PT,
                bbox=dict(boxstyle="round,pad=0.1", fc=WHITE, ec="none"))
    return box


def cell_marker(ax, x, y):
    """a cell value: sky-blue circle (STYLE 6.2)"""
    return ax.plot([x], [y], ls="none", marker="o", ms=5, mfc=SKY, mec=BLACK, mew=0.5, zorder=4)[0]


def face_marker(ax, x, y):
    """a face value: orange triangle (STYLE 6.2)"""
    return ax.plot([x], [y], ls="none", marker="^", ms=5.5, mfc=ORANGE, mec=BLACK, mew=0.5, zorder=4)[0]


def face_flux(ax, x, y, dx=0.0, dy=0.4, color=ORANGE):
    a = FancyArrowPatch((x - 0.5 * dx, y - 0.5 * dy), (x + 0.5 * dx, y + 0.5 * dy), arrowstyle="-|>",
                        mutation_scale=8, lw=1.2, color=color, zorder=5)
    return ax.add_patch(a)


def wall_line(ax, p0, p1):
    """a wall from p0 to p1: thick black line (STYLE 6.2)"""
    return ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=BLACK, lw=2.5, solid_capstyle="butt", zorder=3)[0]


def seam(ax, p0, p1):
    """a block seam: dashed reddish-purple line (STYLE 6.2)"""
    return ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=PURPLE, lw=1.4, ls=(0, (4, 2)), zorder=3)[0]


def bracket(ax, p0, p1, label=None, offset=0.15):
    """a horizontal stencil extent from p0 to p1, offset below (positive offset) or above, with its label"""
    (x0, y0), (x1, y1) = p0, p1
    ax.plot([x0, x0, x1, x1], [y0, y0 - offset, y1 - offset, y1], color=BLACK, lw=0.8)
    if label is not None:
        ax.text(0.5 * (x0 + x1), y0 - 2 * offset, label, fontsize=SMALL_PT, ha="center", va="top")


def slope_guide(ax, x0, y0, x1, order, label=None, color=BLACK):
    """a reference line y ~ x^-order from (x0, y0) to x1, labelled with its order"""
    y1 = y0 * (x1 / x0) ** (-order)
    ax.plot([x0, x1], [y0, y1], color=color, lw=0.8, ls=":")
    ax.text(x1 * 1.05, y1, label or f"$h^{order}$", fontsize=SMALL_PT, va="center", color=color)


def save_to(fig, path):
    """write a figure to `path`, only to look at it outside Quarto (the book draws figures itself)"""
    fig.savefig(path, dpi=DPI, bbox_inches="tight", metadata={"Software": None})


# ---- names of the first version, unchanged until the figure scripts are ported -----------------------------------

def apply():
    """the first version's settings (9 pt serif text, STIX mathtext); legacy, replaced by new_figure() in the port"""
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "lines.linewidth": 1.4,
        "lines.markersize": 4.5,
        "axes.linewidth": 0.8,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "svg.hashsalt": "pyharp-tech-report",  # reproducible SVG ids
        "path.simplify": False,
    })


def save(fig, script_file, svg=False):
    """legacy: write <script>.png (and .svg) next to the script"""
    base = os.path.splitext(os.path.abspath(script_file))[0]
    fig.savefig(base + ".png", metadata={"Software": None})
    if svg:
        fig.savefig(base + ".svg", metadata={"Date": None})
    print(base + ".png")


def cell_box(ax, x, y, width=1., height=1., ghost=False):
    """Shared cell glyph, with hatching for ghosts (STYLE 6.2). Legacy; the house helper is cell()."""
    box = Rectangle((x, y), width, height, edgecolor=BLACK,
                    facecolor="#F7E6EF" if ghost else "#EAF5FC",
                    hatch="//" if ghost else None)
    ax.add_patch(box)
    return box


def cell_value(ax, x, y):
    """legacy; the house helper is cell_marker()"""
    return ax.plot(x, y, 'o', color=SKY)


def face_value(ax, x, y):
    """legacy; the house helper is face_marker()"""
    return ax.plot(x, y, '^', color=ORANGE)


def wall(ax, x, bottom, top):
    """legacy (a vertical wall at x); the house helper is wall_line()"""
    return ax.plot([x, x], [bottom, top], color=BLACK, lw=2.5)
