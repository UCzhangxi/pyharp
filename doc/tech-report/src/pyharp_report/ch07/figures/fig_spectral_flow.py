"""Chapter 7 figure from pyharp f34506f9d14ee7b1f2e1222775baa5093ae6967f.
Historical data: ../data/historical.json, selected from committed native records;
no solver is run. See derivation-checks/ch07/provenance.json for runtime limits.
"""
import json
from pathlib import Path
import numpy as np
from pyharp_report import figstyle as fs

DATA = Path(__file__).resolve().parents[1] / 'data' / 'historical.json'

def make_fig():
    fs.apply()
    fig = fs.Figure(figsize=(fs.DOUBLE, 2.4), layout='constrained')
    ax = fig.subplots()
    ax.set_axis_off()
    for y,word,out,color in [(.76,'Spectral density','Wavenumber trapezoid',fs.BLUE),(.24,'Interval flux','Dimensionless weighted sum',fs.GREEN)]:
        ax.text(.19,y,word,ha='center',va='center',transform=ax.transAxes,
                bbox=dict(boxstyle='round',facecolor=fs.WHITE,edgecolor=color))
        ax.text(.73,y,out,ha='center',va='center',transform=ax.transAxes,
                bbox=dict(boxstyle='round',facecolor=fs.WHITE,edgecolor=color))
        ax.annotate('',xy=(.51,y),xytext=(.36,y),xycoords='axes fraction',arrowprops=dict(arrowstyle='->',color=color))
    ax.annotate('',xy=(.51,.70),xytext=(.36,.30),xycoords='axes fraction',arrowprops=dict(arrowstyle='->',color=fs.VERMILLION,linestyle='--'))
    ax.text(.61,.47,'Extra width factor',color=fs.VERMILLION,ha='center',transform=ax.transAxes)
    return fig
