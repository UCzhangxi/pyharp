"""ch09 figure: how an installed pyharp finds pydisort's library (a cartoon; no data).

pyharp's extension module loads libharp_release.so, which needs libdisort_release.so and finds it through an
absolute search path into the pydisort installation pyharp was built against; pydisort's own module needs the
same soname. One copy is loaded, and both pyharp and pydisort use it.
"""
from matplotlib.patches import FancyArrowPatch

from pyharp_report import figstyle as fs

BOXES = [(0.0, 1.6, "pyharp module\npyharp.*.so"), (0.0, 0.0, "pyharp library\nlibharp_release.so"),
         (4.6, 0.0, "libdisort_release.so\n(installed pydisort)"), (4.6, 1.6, "pydisort module\npydisort.*.so")]


def make_fig():
    fig, ax = fs.new_figure("double", 1.9)
    fs.cartoon(ax)
    w, h = 2.4, 0.8
    for x, y, lab in BOXES:
        fs.cell(ax, x, y, w, h, fill=True)
        ax.text(x + w / 2, y + h / 2, lab, ha="center", va="center", fontsize=fs.SMALL_PT)
    arrows = [((1.2, 1.6), (1.2, 0.8), "needs", "left"), ((2.4, 0.4), (4.6, 0.4), "absolute search path", "center"),
              ((5.8, 1.6), (5.8, 0.8), "needs", "left")]
    for p0, p1, lab, ha in arrows:
        ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=8, lw=1.0, color=fs.BLACK))
        dx = 0.1 if ha == "left" else 0.0
        ax.text(0.5 * (p0[0] + p1[0]) + dx, 0.5 * (p0[1] + p1[1]) + 0.08, lab, ha=ha, va="bottom",
                fontsize=fs.SMALL_PT)
    ax.text(3.5, 2.55, "one copy of libdisort is loaded; its type layout must match the headers pyharp was "
            "compiled against", ha="center", va="bottom", fontsize=fs.SMALL_PT, color=fs.VERMILLION)
    ax.set_xlim(-0.1, 7.1)
    ax.set_ylim(-0.1, 2.9)
    return fig
