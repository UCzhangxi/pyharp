"""Chapter 8 dependency map: the five sections and how they use each other (a cartoon, no data).

An arrow is labelled "requires" or "optional"; the actinic-flux node is dashed because pyharp computes none at the
pin of code_pin.yml. The code facts behind each edge are cited in the chapter text.
"""
from pyharp_report import figstyle as fs
from pyharp_report.ch08.figures._boxes import arrow, box


def make_fig():
    fig, ax = fs.new_figure("double", 2.4)
    fs.cartoon(ax)
    box(ax, 1.6, 2.4, "configuration file\n(RadiationOptions.from_yaml)", w=3.0)
    box(ax, 5.2, 2.4, "sum of the bands\n(Radiation.forward)", fs.GREEN, w=2.5)
    box(ax, 8.8, 2.4, "bands: DISORT or Toon\n(chapters 3 and 4)", fs.GREY, w=2.6)
    box(ax, 5.2, 0.6, "spherical scaling\n(area, vol, dz in atm)", w=2.5)
    box(ax, 1.6, 0.6, "column stepper\n(RadiationModel, Integrator)", w=3.0)
    box(ax, 8.8, 0.6, "actinic flux\n(not computed)", fs.VERMILLION, w=2.6, ls="--")
    arrow(ax, (3.15, 2.4), (3.9, 2.4), "builds", dy=0.25)
    arrow(ax, (6.5, 2.4), (7.45, 2.4), "requires", dy=0.25)
    arrow(ax, (5.2, 1.98), (5.2, 1.02), "optional", dx=0.6)
    arrow(ax, (1.6, 1.02), (4.0, 2.02), "requires", dx=-0.4, dy=0.2)
    arrow(ax, (8.8, 1.98), (8.8, 1.02), "DISORT only,\nthrough pydisort", fs.VERMILLION, dx=-1.0, ls="--")
    ax.set_xlim(0.0, 10.2)
    ax.set_ylim(0.0, 3.0)
    return fig
