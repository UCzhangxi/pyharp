"""The radiation configuration file and the options objects it becomes (a cartoon, no data).

Left: the top-level keys of the YAML file; right: the objects RadiationOptions.from_yaml and
IntegratorOptions.from_yaml build from them, and the keys each reads. Code facts: radiation.cpp, radiation_band.cpp and
integrator.cpp at the pin of code_pin.yml, cited in the chapter text.
"""
from pyharp_report import figstyle as fs
from pyharp_report.ch08.figures._boxes import arrow, box

KEYS = [("species", 3.3), ("geometry: cells", 2.5), ("opacities", 1.7), ("bands", 0.9), ("integration", 0.1)]


def make_fig():
    fig, ax = fs.new_figure("double", 2.6)
    fs.cartoon(ax)
    for k, y in KEYS:
        ax.text(0.3, y, k, ha="left", va="center", fontsize=fs.SMALL_PT, family=fs.MONO)
    box(ax, 5.4, 3.3, "species_names, species_weights\n(process-wide)", w=3.9)
    box(ax, 5.4, 1.7, "RadiationBandOptions, one per band:\nnwave, nstr, solver, flags, range,\n"
        "nlyr = nx1, ncol = nx2 nx3", fs.GREEN, w=3.9, h=1.15)
    box(ax, 5.4, 0.1, "IntegratorOptions:\ntype, cfl, tlim, nlim, ncycle_out", w=3.9)
    box(ax, 9.3, 1.7, "OpacityOptions\n(chapter on assembly)", fs.GREY, w=2.4)
    arrow(ax, (1.75, 3.3), (3.4, 3.3))
    arrow(ax, (2.0, 2.5), (3.4, 1.95))
    arrow(ax, (1.45, 1.7), (3.4, 1.7))
    arrow(ax, (1.05, 0.9), (3.4, 1.45))
    arrow(ax, (1.5, 0.1), (3.4, 0.1))
    arrow(ax, (7.4, 1.7), (8.05, 1.7))
    ax.text(5.4, -0.6, "not read: weight or wavenumber grid, units, outdirs, max_redo", ha="center", va="center",
            fontsize=fs.SMALL_PT, color=fs.VERMILLION)
    ax.set_xlim(0.0, 10.6)
    ax.set_ylim(-0.85, 3.75)
    return fig
