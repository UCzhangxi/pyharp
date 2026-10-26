#!/usr/bin/env python3
"""Independent Decimal mixture oracle against compiled pinned RadiationBand.

Extinction units m^-1; layer thickness m; tau, SSA and Legendre moments
dimensionless. Moments stored by pyharp begin at beta_1, not beta_0.
The oracle sums absorption/scattering contributions using Decimal arithmetic;
it does not call Torch or translate the native implementation into Python.
"""
import argparse
import os
import csv
from decimal import Decimal, getcontext
import json
import math
from pathlib import Path
import struct
import subprocess

getcontext().prec = 80
D = Decimal
ROOT = Path(__file__).resolve().parent
PIN = 'f34506f9d14ee7b1f2e1222775baa5093ae6967f'


def cast(x, bits):
    return struct.unpack('f', struct.pack('f', float(x)))[0] if bits == 32 else float(x)


def generate():
    cases = []
    for bits in (64, 32):
        def add(name, sources, dz=('2',), shape=(1, 1, 1), dzdim=1):
            nw, nc, nl = shape
            n = nw * nc * nl
            # Each source can be a constant tuple or a list of cell tuples.
            arrays = [s if isinstance(s, list) else [s] * n for s in sources]
            cases.append(dict(name=name, bits=bits, shape=shape,
                              sources=arrays, dz=list(dz), dzdim=dzdim,
                              np=max([3]+[len(s[0]) for s in arrays])))

        add('absorption_only', [('2',), ('3',)])
        add('extinction_only_layout', [('2',), ('3',)])
        cases[-1]['np']=1
        add('extinction_ssa_layout', [('2','.5'), ('3',)])
        cases[-1]['np']=2
        add('zero_scattering', [('2', '0', '.8', '.64', '.512'), ('3', '0', '-.5', '.25')])
        add('vacuum', [('0', '1', '.9', '.81'), ('0', '.3', '-.5', '.25')])
        add('no_sources', [])
        add('isotropic_scattering', [('2', '.5'), ('1',)])
        # P_Rayleigh=1 + (1/2)P_2, hence unscaled moment beta_2=1/10.
        add('rayleigh_hg', [('3','1','0','.1','0'), ('2','.5','.6','.36','.216')])
        add('moment_cancellation', [('1','1','.5','.25'),('1','1','-.5','.25')])
        add('tiny_positive_scattering', [('1','1e-100' if bits==64 else '1e-20','.7','.49')])
        # E=10, S=2*.5+3*.8=3.4; beta1=(1*.6+2.4*(-.2))/3.4=3/85.
        add('mixed_hg_absorber', [('2', '.5', '.6', '.36', '.216'),
                                  ('3', '.8', '-.2', '.04', '-.008'), ('5',)])
        add('mixed_reverse_order', [('5',), ('3', '.8', '-.2', '.04', '-.008'),
                                   ('2', '.5', '.6', '.36', '.216')])
        add('moment_padding', [('2', '.5', '.6', '.36', '.216'), ('3', '.8', '-.2')])
        add('conservative_forward', [('2', '1', '1', '1', '1')])
        add('conservative_backward', [('2', '1', '-1', '1', '-1')])
        add('conservative_isotropic', [('2', '1', '0', '0', '0')])
        margin = D('1e-12') if bits == 64 else D('1e-6')
        for label, gap in [('above_cap', margin/2), ('at_cap', margin), ('below_cap', margin*2)]:
            add(label, [('2', str(1-gap), '.75', '.5625')])
        add('absorber_dilutes_scattering', [('2', '1', '.5', '.25'), ('2000',)])
        add('zero_thickness', [('2', '.5', '.7', '.49')], dz=('0',))
        add('thin_thick_layers', [[('2', '.5', '.7', '.49')]*3], dz=('1e-9','1','1e9'),shape=(1,1,3))
        for scale in ('1e-120', '1e120') if bits == 64 else ('1e-15', '1e15'):
            add('scale_'+scale, [(str(D(2)*D(scale)),'.5','.6','.36'),
                                 (str(D(3)*D(scale)),'.8','-.2','.04')],dz=(str(1/D(scale)),))
        # Heterogeneous 2-wave x 2-column x 3-layer batch includes vacuum,
        # zero scattering and conservative cells. Vary moments independently.
        a=[]; b=[]
        for i in range(12):
            a.append((str(i%4), ['0','.5','1'][i%3], str(D(i%5)/10), '.2'))
            b.append((str((i+1)%3),))
        add('batch_dz1', [a,b], dz=('0','2','5'), shape=(2,2,3))
        add('batch_dz2', [a,b], dz=('0','2','5','3','7','11'), shape=(2,2,3), dzdim=2)
        # Same physical mixture split across two artificial opacity sources.
        add('split_source', [('1','.5','.6','.36','.216'),('1','.5','.6','.36','.216'),
                              ('3','.8','-.2','.04','-.008'),('5',)])
        # Individual cells independently exercise the same batch values.
        for i in range(12):
            add('cell_'+str(i), [a[i],b[i]], dz=(['0','2','5','3','7','11'][i%6],))
    return cases


def expected(case):
    bits = case['bits']
    dec = lambda x: D.from_float(cast(x, bits))
    nw,nc,nl = case['shape']
    cap = dec(1.0-(1e-12 if bits==64 else 1e-6))
    values=[]; physical=[]
    for i in range(nw*nc*nl):
        src = [[dec(v) for v in s[i]] for s in case['sources']]
        # Derive total extinction from absorption plus scattering coefficients.
        scattering = sum((s[0]*s[1] for s in src if len(s)>1), D(0))
        absorption = sum((s[0]*(1-s[1]) if len(s)>1 else s[0] for s in src), D(0))
        extinction = absorption+scattering
        z = dec(case['dz'][i%nl if case['dzdim']==1 else i%(nc*nl)])
        omega = scattering/extinction if extinction else D(0)
        row = [extinction*z, min(omega,cap)]
        for m in range(2,case['np']):
            row.append(sum((s[0]*s[1]*s[m] for s in src if len(s)>m),D(0))/scattering
                       if scattering else D(0))
        values.extend(map(float,row[:case['np']]))
        physical.extend(map(float,([extinction*z,omega]+row[2:])[:case['np']]))
    return values,physical


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--driver',type=Path,default=ROOT/'assembly_driver')
    args=parser.parse_args()
    repo=Path(os.environ['PYHARP_WT'])
    head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    if head!=PIN: raise RuntimeError('Source pin moved: '+head)
    cases=generate()
    with (ROOT/'fixtures.txt').open('w') as f:
        f.write(str(len(cases))+'\n')
        for c in cases:
            f.write(' '.join(map(str,[c['name'],c['bits'],*c['shape'],c['np'],len(c['sources']),c['dzdim']]))+'\n')
            for s in c['sources']:
                f.write(str(len(s[0]))+' '+' '.join(str(v) for cell in s for v in cell)+'\n')
            f.write(' '.join(map(str,c['dz']))+'\n')
    subprocess.run([str(args.driver.resolve()),str(ROOT/'fixtures.txt'),str(ROOT/'actual.csv')],check=True)
    rows=list(csv.DictReader((ROOT/'actual.csv').open()))
    result=[]; offset=0
    for c in cases:
        exp,phy=expected(c); obs=rows[offset:offset+len(exp)]; offset+=len(exp)
        atol,rtol=(5e-15,5e-14) if c['bits']==64 else (3e-7,3e-6)
        errs=[]; scaled=[]; deviations=[]; relative=[]; exact_limits=True
        for i,(r,e,p) in enumerate(zip(obs,exp,phy)):
            assert r['case']==c['name'] and int(r['dtype'])==c['bits'] and int(r['index'])==i
            a=float(r['actual']); err=abs(a-e)
            if not math.isfinite(a): err=math.inf
            errs.append(err); scaled.append(err/(atol+rtol*abs(e))); deviations.append(abs(a-p))
            if e != 0:
                relative.append(err/abs(e))
                # An absolute tolerance alone cannot detect loss of tiny SSA.
                if abs(e)<atol: exact_limits = exact_limits and err<=rtol*abs(e)
            if i%c['np']==1 and c['name'] in ('conservative_forward','conservative_backward',
                    'conservative_isotropic','above_cap','at_cap'):
                exact_limits = exact_limits and a==e
        invariants=all(float(r[k])==0 for r in obs for k in ('repeat_error','source_error','capture_error'))
        result.append(dict(case=c['name'],dtype=c['bits'],scalars=len(exp),atol=atol,rtol=rtol,
                           max_abs_error=max(errs),max_tolerance_fraction=max(scaled),
                           max_relative_error=max(relative,default=0),
                           max_physical_deviation=max(deviations),invariants=invariants,
                           exact_limits=exact_limits,passed=max(scaled)<=1 and invariants and exact_limits))
    assert offset==len(rows)
    # Check metamorphic properties using native outputs, independently of oracle.
    actual={}
    for r in rows: actual.setdefault((r['case'],int(r['dtype'])),[]).append(float(r['actual']))
    metamorphic=[]
    for bits in (64,32):
        tol=5e-14 if bits==64 else 3e-6
        for name in ('mixed_reverse_order','split_source'):
            error=max(abs(x-y) for x,y in zip(actual[(name,bits)],actual[('mixed_hg_absorber',bits)]))
            metamorphic.append(dict(check=name,dtype=bits,error=error,tolerance=tol,passed=error<=tol))
        batched=actual[('batch_dz2',bits)]
        singles=[v for i in range(12) for v in actual[('cell_'+str(i),bits)]]
        error=max(abs(x-y) for x,y in zip(batched,singles))
        metamorphic.append(dict(check='batch_equals_cells',dtype=bits,error=error,tolerance=tol,passed=error<=tol))
    summary=dict(pin=PIN,device='cpu',oracle='Decimal 80-digit on dtype-rounded input',
                 cases=len(result),scalars=len(rows),passed=sum(r['passed'] for r in result),
                 failed=sum(not r['passed'] for r in result),results=result,metamorphic=metamorphic)
    (ROOT/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (ROOT/'results.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(result[0])); w.writeheader(); w.writerows(result)
    for bits in (64,32):
        rs=[r for r in result if r['dtype']==bits]
        print(f"float{bits}: {sum(r['passed'] for r in rs)}/{len(rs)} passed, max_abs_error={max(r['max_abs_error'] for r in rs):.17g}, max_tolerance_fraction={max(r['max_tolerance_fraction'] for r in rs):.6g}")
    print(f"{len(rows)} scalar comparisons; {sum(r['passed'] for r in metamorphic)}/{len(metamorphic)} metamorphic checks")
    for r in result:
        if not r['passed']: print('FAILED',r)
    return int(summary['failed']>0 or not all(r['passed'] for r in metamorphic))


if __name__=='__main__':
    raise SystemExit(main())
