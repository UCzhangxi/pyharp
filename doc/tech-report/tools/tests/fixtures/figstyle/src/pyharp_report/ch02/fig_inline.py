import matplotlib
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

plt.rcParams["font.size"] = 7
matplotlib.rcParams.update({"font.family": "serif"})


def make_fig():
    fig, ax = plt.subplots(figsize=(3.4, 2))
    ax.text(0, 0, "a", fontsize=7)
    ax.text(0, 1, "b", family="monospace")
    ax.set_title("t", size=8)
    ax.legend(prop={"size": 6})
    ax.tick_params(labelsize=6)
    FontProperties(size=6)
    ax.plot([0, 1], [0, 1], markersize=4)
    return fig
