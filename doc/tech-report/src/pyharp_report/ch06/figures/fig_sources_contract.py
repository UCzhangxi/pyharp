"""ch06 figure: the tensor every opacity source returns and how the band uses its columns (a cartoon; no data).

Layout from the forward() of the source modules (src/opacity/rayleigh.cpp, water_liquid_mie.cpp, picaso_ck.cpp) at
the code pin of code_pin.yml: shape (nwave, ncol, nlyr, nprop), column 0 extinction [1/m], column 1
single-scattering albedo, columns 2 .. 1 + nmom the phase moments chi_1 .. chi_nmom.
"""
from pyharp_report import figstyle as fs

COLS = [("k", "extinction\n[m$^{-1}$]"), (r"$\omega$", "albedo\n[-]"), (r"$\chi_1$", ""), (r"$\chi_2$", ""),
        (r"$\cdots$", ""), (r"$\chi_{n}$", "")]


def over(ax, x0, x1, y, label):
    """an upward bracket over the columns x0..x1 at height y, labelled above"""
    ax.plot([x0, x0, x1, x1], [y - 0.08, y, y, y - 0.08], color=fs.BLACK, lw=0.8)
    ax.text(0.5 * (x0 + x1), y + 0.04, label, ha="center", va="bottom", fontsize=fs.SMALL_PT)


def make_fig():
    fig, ax = fs.new_figure("double", 1.9)
    fs.cartoon(ax)
    w = 0.75
    for i, (sym, lab) in enumerate(COLS):
        x = 1.6 + i * w
        fs.cell(ax, x, 0.7, w, 0.6, fill=i < 2)
        ax.text(x + w / 2, 1.0, sym, ha="center", va="center", fontsize=fs.LABEL_PT)
        if lab:
            ax.text(x + w / 2, 0.62, lab, ha="center", va="top", fontsize=fs.SMALL_PT)
    ax.text(1.5, 1.0, "(nwave, ncol, nlyr,", ha="right", va="center", fontsize=fs.SMALL_PT, family=fs.MONO)
    ax.text(1.6 + 6 * w + 0.1, 1.0, ")", ha="left", va="center", fontsize=fs.SMALL_PT, family=fs.MONO)
    over(ax, 1.6, 1.6 + w, 1.4, "absorption only: nprop = 1")
    over(ax, 1.6, 1.6 + 6 * w, 1.8, "scattering: nprop = 2 + nmom")
    ax.text(1.6 + 2 * w + 1.5 * w, 0.62, "phase moments [-]", ha="center", va="top", fontsize=fs.SMALL_PT)
    ax.set_xlim(-0.1, 7.0)
    ax.set_ylim(0.1, 2.2)
    return fig
