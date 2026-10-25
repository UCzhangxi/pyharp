"""ch06 figure: the opacity sources of the chapter and where their output goes (a cartoon; no data)."""
from matplotlib.patches import FancyArrowPatch

from pyharp_report import figstyle as fs

SOURCES = [("rayleigh", "Rayleigh gas\nscattering"), ("water-liquid-mie", "liquid-water\ndroplets, Mie"),
           ("picaso-ck", "pre-mixed\nk table"), ("helios", "Helios table\n(refused)")]


def make_fig():
    fig, ax = fs.new_figure("double", 2.0)
    fs.cartoon(ax)
    w, h = 1.3, 0.62
    fs.cell(ax, 0.0, 0.95, 1.4, 0.7, fill=True)
    ax.text(0.7, 1.42, "opacities:", ha="center", va="center", fontsize=fs.SMALL_PT, family=fs.MONO)
    ax.text(0.7, 1.15, "one entry,\nits type", ha="center", va="center", fontsize=fs.SMALL_PT)
    for i, (key, lab) in enumerate(SOURCES):
        x = 2.0 + i * 1.45
        refused = key == "helios"
        fs.cell(ax, x, 0.95, w, h, fill=not refused)
        ax.text(x + w / 2, 0.95 + h / 2, lab, ha="center", va="center", fontsize=fs.SMALL_PT,
                color=fs.VERMILLION if refused else fs.BLACK)
        ax.text(x + w / 2, 0.95 + h + 0.06, key, ha="center", va="bottom", fontsize=fs.SMALL_PT, family=fs.MONO)
        if not refused:
            ax.add_patch(FancyArrowPatch((x + w / 2, 0.95), (x + w / 2, 0.45), arrowstyle="-|>", mutation_scale=8,
                                         lw=1.0, color=fs.BLACK))
    ax.add_patch(FancyArrowPatch((1.4, 1.3), (2.0, 1.3), arrowstyle="-|>", mutation_scale=8, lw=1.0, color=fs.BLACK))
    fs.cell(ax, 2.0, -0.05, 4.2, 0.5, fill=True)
    ax.text(4.1, 0.2, r"$k$, $\omega$, $\chi_l$ of each source, summed by the band", ha="center", va="center",
            fontsize=fs.SMALL_PT)
    ax.set_xlim(-0.1, 7.9)
    ax.set_ylim(-0.15, 1.95)
    return fig
