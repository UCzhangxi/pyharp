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
    data=json.loads(DATA.read_text())['assembly']
    fs.apply()
    fig = fs.Figure(figsize=(fs.DOUBLE, 2.7), layout='constrained')
    ax = fig.subplots()
    for bits,color,marker in [(64,fs.BLUE,'o'),(32,fs.ORANGE,'s')]:
        values=[r['max_tolerance_fraction'] for r in data if r['dtype']==bits]
        ax.plot(np.arange(1,len(values)+1),values,marker=marker,color=color,
                markersize=3,linewidth=.7,label=f'float{bits}')
    ax.axhline(1,color=fs.BLACK,linestyle='--',label='threshold')
    ax.set_xlabel('Fixture index [-]'); ax.set_ylabel('Error / allowed error [-]')
    ax.legend(ncol=3)
    return fig
