"""Verify saved eigenpairs by solving K*u=lambda*M*phi through OpenSees."""
import argparse
import json
from pathlib import Path
import numpy as np
import openseespy.opensees as ops
from structural_ai.opensees_runner import build, configure
from structural_ai.provenance import file_hash, write_json


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('model',type=Path)
    p.add_argument('results',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    m=json.loads(a.model.read_text())
    summary=json.loads((a.results/'summary.json').read_text())
    mass={n['node']:np.array(n['mass']) for n in m['nodal_masses']}
    checks=[]
    for mode in summary['modes']:
        i=mode['mode']
        saved=np.loadtxt(a.results/f'mode_{i:02d}_nodes.csv',delimiter=',',skiprows=1)
        phi={int(row[0]):row[4:] for row in saved}
        build(ops,m)
        ops.timeSeries('Linear',1);ops.pattern('Plain',1,1)
        for node, v in mass.items():
            ops.load(node,*(mode['eigenvalue_rad2_s2']*v*phi[node]).tolist())
        configure(ops,m)
        code=ops.analyze(1)
        if code:raise RuntimeError('Eigenpair static verification failed')
        expected=np.array([phi[n['id']] for n in m['nodes']])
        actual=np.array([ops.nodeDisp(n['id']) for n in m['nodes']])
        relative=float(np.linalg.norm(actual-expected)/np.linalg.norm(expected))
        checks.append({'mode':i,'return_code':code,'relative_displacement_residual':relative,
                       'passed':bool(np.isfinite(relative) and relative<1e-7)})
        print(checks[-1],flush=True)
    write_json(a.output,{'engine':'OpenSeesPy','version':ops.version(),
        'model_sha256':file_hash(a.model),'checks':checks,
        'passed':all(v['passed'] for v in checks),'engineering_approval':False})
    ops.wipe()
    raise SystemExit(0 if all(v['passed'] for v in checks) else 1)
