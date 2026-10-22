from pyharp_report import figstyle as fs


def make_fig():
    fig, ax = fs.new_figure("single", 2.0)
    ax.text(0, 0, "a", fontsize=fs.SMALL_PT, color=fs.BLACK)
    ax.set_xlabel("x", size=fs.LABEL_PT)
    return fig
