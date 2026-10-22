from pyharp_report.ch03 import _style as fs
from pyharp_report.ch03._style import BLACK, new_figure


def make_fig():
    fig, ax = new_figure("single", 2.0)
    ax.text(0, 0, "a", fontsize=fs.SMALL_PT, color=BLACK)
    return fig
