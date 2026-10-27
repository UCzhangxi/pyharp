#!/usr/bin/env python3
"""Audit stored chapter 7 measurements and exact identities, without loading a solver.

Formulas: pyharp f34506f9d14ee7b1f2e1222775baa5093ae6967f;
pydisort source 8af15242a265a60ea6fb51c29d48e6688a63ab67.
Run: python derivation-checks/ch07_evidence_check.py (any working directory).
PASS validates the record/identity, not a solver fix. Known failures remain failures.
Needs Python 3.10 or later (zip(strict=True)); the standard library is the only dependency.
"""
import csv
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

if sys.version_info < (3, 10):
    sys.exit(f'ch07_evidence_check: needs Python 3.10 or later, found {sys.version.split()[0]}')

ROOT = Path(__file__).resolve().parent / 'ch07'

def read(path):
    return json.loads((ROOT / path).read_text())

def check_C1_integrity():
    files = read('provenance.json')['files']
    for name, item in files.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == item['sha256'], name
    report = ROOT.parent.parent
    figure_data = json.loads((report/'src/pyharp_report/ch07/data/historical.json').read_text())
    assert figure_data['assembly'] == read('assembly/results.json')['results']
    expected = [r for r in read('spectral/results_b_band.json')['grid'][:120] if r['solver']=='disort' and r['nwave']==128]
    assert figure_data['spectral'] == expected
    print(f'[C1] PASS artifact integrity: {len(files)} files; original/transformed hashes recorded')

def check_C2_assembly():
    spec = importlib.util.spec_from_file_location('assembly_oracle', ROOT/'assembly/check_assembly.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # definitions only: main() and the native driver are NOT run
    cases = mod.generate()
    rows = list(csv.DictReader((ROOT/'assembly/actual.csv').open()))
    saved = read('assembly/results.json')
    offset = 0
    for case, record in zip(cases, saved['results'], strict=True):
        expected, _ = mod.expected(case)
        atol, rtol = (5e-15, 5e-14) if case['bits'] == 64 else (3e-7, 3e-6)
        for i, e in enumerate(expected):
            row = rows[offset+i]
            assert row['case'] == case['name'] and int(row['dtype']) == case['bits']
            assert int(row['index']) == i
            a = float(row['actual'])
            assert abs(a-e) <= atol+rtol*abs(e)
            if 0 < abs(e) < atol:
                assert abs(a-e) <= rtol*abs(e)
            assert all(float(row[k]) == 0 for k in ['repeat_error','source_error','capture_error'])
        assert record['passed']
        offset += len(expected)
    assert offset == len(rows) == saved['scalars']
    actual = {}
    for r in rows:
        actual.setdefault((r['case'],int(r['dtype'])), []).append(float(r['actual']))
    for record in saved['metamorphic']:
        bits, name = record['dtype'], record['check']
        if name == 'batch_equals_cells':
            a = actual[('batch_dz2', bits)]
            b = [v for i in range(12) for v in actual[('cell_'+str(i),bits)]]
        else:
            a, b = actual[(name,bits)], actual[('mixed_hg_absorber',bits)]
        error = max(abs(x-y) for x,y in zip(a,b,strict=True))
        assert error <= record['tolerance'] and record['passed']
    print(f"[C2] PASS historical assembly: {len(cases)}/{len(cases)} cases; {offset} scalars; {len(saved['metamorphic'])}/6 metamorphic")
    for bits in [64,32]:
        rr = [r for r in saved['results'] if r['dtype']==bits]
        print(f"[C2] float{bits}: max_abs={max(r['max_abs_error'] for r in rr):.8g}; max_rel={max(r['max_relative_error'] for r in rr):.8g}")

def check_C3_spectral_pairs():
    rows = read('spectral/results_b_band.json')['grid']
    maxima = []
    for subset, stride in [(rows[:120],3),(rows[120:],2)]:
        errors=[]
        for start in range(0,len(subset),stride):
            w,n = subset[start:start+2]
            assert (w['mode'],n['mode']) == ('weight','wavenumber')
            for key in ['solver','dnu','nwave','nstr','albedo','kext']:
                assert w[key] == n[key]
            errors.append(abs(n['ratio']/w['ratio']/w['dnu']-1))
        # Division and sums of <=128 positive terms: 1e-12 exceeds 1000 eps64.
        assert max(errors) < 1e-12
        maxima.append(max(errors))
        print(f'[C3] PASS historical width-factor identity: {len(errors)} pairs; error={max(errors):.8g} < 1e-12')
    for r in rows[:120]:
        if r['solver']=='disort' and r['nwave']==128:
            print(f"[C3] width={r['dnu']:g} mode={r['mode']} flux/reference={r['measured']/r['reference']:.8g}")

def check_C4_known_failures():
    a = read('spectral/results_a_planck.json')['checks']
    failed = []
    for r in a:
        rel = abs(r['measured']/r['reference']-1)
        assert (rel <= r['tol']) == r['pass']
        if not r['pass']: failed.append(r['id'])
    assert len(failed)==4
    c = read('spectral/results_c_accum.json')['C6']
    assert c['band_total']==0 and c['per_point_spectrum']>0
    print(f"[C4] PASS failure preservation: {len(a)-len(failed)} Planck assertions pass, {len(failed)} FAIL; single-point total=0 with nonzero spectrum")
    for name in failed: print('[C4] recorded FAIL: '+name)

def check_C5_weights():
    rows = read('spectral/results_d_bins.json')['rows']
    good = [r for r in rows if r['convention']=='ck']
    assert good
    for r in good: assert abs(r['measured']/r['reference']-1)<1e-4
    print(f'[C5] PASS historical normalized-bin controls: {len(good)} rows; max_relative_error={max(abs(r["measured"]/r["reference"]-1) for r in good):.8g} < 1e-4')

def check_C6_planck_sum():
    data = read('spectral/results_f_norm.json')
    for r in data['rows']: assert abs(r['pi_sum']/data['sigma_T4']-1)<1e-4
    print(f'[C6] PASS historical Planck bin sums: {len(data["rows"])} tilings; relative_error < 1e-4')

def check_C7_exact_identities():
    scattering = Q(2)*Q(1,2)+Q(3)*Q(4,5)
    moments = [(Q(1)*Q(3,5)**l+Q(12,5)*Q(-1,5)**l)/scattering for l in [1,2,3]]
    assert scattering==Q(17,5) and moments==[Q(3,85),Q(57,425),Q(123,2125)]
    # tau and omega are printed below, so assert them too: k = 2+3+5, dz = 2.
    extinction, thickness = Q(2)+Q(3)+Q(5), Q(2)
    assert extinction*thickness==Q(20) and scattering/extinction==Q(17,50)
    # P2(x)=(3x^2-1)/2: integral P2^2 dx = (9*2/5-6*2/3+2)/4.
    norm = (Q(18,5)-4+2)/4
    assert norm/4 == Q(1,10)  # half moment integral of P=1+P2/2
    x=[Q(600),Q(630),Q(710),Q(800)]
    density=[2*t+3 for t in x]
    trap=sum((b-a)*(fa+fb)/2 for a,b,fa,fb in zip(x,x[1:],density,density[1:]))
    assert trap==(x[-1]**2+3*x[-1])-(x[0]**2+3*x[0])
    width=x[-1]-x[0]
    integrated=Q(7)
    assert sum((b-a)*integrated for a,b in zip(x,x[1:]))==width*integrated
    print('[C7] PASS exact rational identities: mixture tau=20 omega=17/50 chi=(3/85,57/425,123/2125); Rayleigh chi2=1/10; trapezoid exact for affine density; repeated integral gains width')

def main():
    failures=0
    for function in [check_C1_integrity,check_C2_assembly,check_C3_spectral_pairs,check_C4_known_failures,check_C5_weights,check_C6_planck_sum,check_C7_exact_identities]:
        try: function()
        except Exception as exc:
            failures+=1
            print(f'FAIL {function.__name__}: {exc!r}')
    return failures

if __name__=='__main__':
    raise SystemExit(main())
