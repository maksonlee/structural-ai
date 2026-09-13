# Imported A01 R06 code; retain the MIT notice in LICENSES/A01-R06-original.txt.
"""OpenSees adapter; numerical diagnostics are separate from design approval.

See docs/validation.md for benchmark derivations and force conventions.
"""
from __future__ import annotations
import argparse,csv,json,math,sys
from pathlib import Path
import numpy as np
from .provenance import write_json
from .joint_constraints import validate_constraints, recover_constraints


def resultant(xyz, records):
    """Global force and moment about (0,0,0), including r cross F."""
    total = np.zeros(6)
    for node, vector in records:
        v = np.asarray(vector, dtype=float)
        if v.shape != (6,) or not np.isfinite(v).all():
            raise ValueError('Nonfinite or invalid nodal force vector')
        total += np.r_[v[:3], v[3:] + np.cross(xyz[node], v[:3])]
    return total


def response(ops, element, query, size):
    values = np.asarray(ops.eleResponse(element, query), dtype=float)
    if values.shape != (size,) or not np.isfinite(values).all():
        raise RuntimeError(f'Invalid {query} response for element {element}')
    return values


def static_checks(ops, m, case, xyz):
    """Independently assemble nodal residuals from actual element end forces."""
    ops.reactions()
    nodal = {n['id']: np.zeros(6) for n in m['nodes']}
    for e in m['elements']:
        forces = response(ops, e['id'], 'forces', 6*len(e['nodes']))
        for node, v in zip(e['nodes'], forces.reshape(-1, 6)):
            nodal[node] += v
    loads = m['load_cases'][case]['nodal_loads']
    for ld in loads:
        nodal[ld['node']] -= ld['vector']
    reactions = [(s['node'], ops.nodeReaction(s['node'])) for s in m['supports']]
    for node, v in reactions:
        nodal[node] -= v
    applied = resultant(xyz, [(ld['node'], ld['vector']) for ld in loads])
    base = resultant(xyz, reactions)
    residual = applied + base
    # Diagnostic numerical tolerances, not building-code criteria.
    scale = max(1., sum(np.linalg.norm(ld['vector'][:3]) for ld in loads))
    length = max(1., max(np.linalg.norm(p) for p in xyz.values()))
    limits = np.array([scale]*3 + [scale*length]*3)*1e-7
    disp = np.array([ops.nodeDisp(n['id']) for n in m['nodes']])
    if not np.isfinite(disp).all():
        raise RuntimeError('Nonfinite displacement')
    reduced, actions, joint_error = recover_constraints(
        m, xyz, nodal, {n['id']: d for n, d in zip(m['nodes'], disp)})
    local_max = np.max(np.abs(list(reduced.values())), axis=0)
    return {
        'applied_force_kN': applied[:3].tolist(),
        'base_reaction_force_kN': base[:3].tolist(),
        'applied_moment_about_origin_kNm': applied[3:].tolist(),
        'base_moment_about_origin_kNm': base[3:].tolist(),
        'equilibrium_residual_kN_kNm': residual.tolist(),
        'nodal_residual_max_kN_kNm': local_max.tolist(),
        'tolerances_kN_kNm': limits.tolist(),
        'numerical_checks_passed': bool(np.all(abs(residual) <= limits) and np.all(local_max <= limits)
                                      and np.all(joint_error <= 1e-10)),
        'rigid_joint_count': len(actions),
        'rigid_joint_compatibility_max_m_rad': joint_error.tolist(),
        'joint_actions': actions,
        'max_abs_translation_mm': (abs(disp[:, :3]).max(0)*1000).tolist(),
        'floor_mean_translation_mm': {
            level: (np.mean([ops.nodeDisp(n['id'])[:3] for n in m['nodes']
                             if abs(n['xyz'][2]-z) < 1e-7], axis=0)*1000).tolist()
            for level, z in m.get('levels_m', {}).items()
        },
    }

def build(ops,m):
    ops.wipe();ops.model('basic','-ndm',3,'-ndf',6)
    xyz={n['id']:np.array(n['xyz']) for n in m['nodes']}
    for n in m['nodes']:ops.node(n['id'],*n['xyz'])
    for s in m['supports']:ops.fix(s['node'],*s['fixity'])
    for link in validate_constraints(m, xyz):
        ops.rigidLink('beam', link['master'], link['slave'])
    for a in m['nodal_masses']:ops.mass(a['node'],*a['mass'])
    E=m['materials']['E_kN_m2']; nu=m['materials']['poisson']; G=E/(2*(1+nu))
    sectags={}
    for key,s in m['sections'].items():
        if 't' in s:
            tag=len(sectags)+1;sectags[key]=tag
            ops.section('ElasticMembranePlateSection',tag,E*s.get('E_factor',1),nu,s['t'],0.0)
    transf={}
    for e in m['elements']:
        s=m['sections'][e['section']]
        if e['kind']=='shell':ops.element('ShellMITC4',e['id'],*e['nodes'],sectags[e['section']])
        elif e['kind']=='frame':
            a,b=[xyz[n] for n in e['nodes']];x=(b-a)/np.linalg.norm(b-a)
            y=np.array(e['local_y']);y=y-x*np.dot(x,y);y=y/np.linalg.norm(y);z=np.cross(x,y)
            offset=e.get('offset',[0.,0.,0.]);key=tuple(np.round(np.r_[z,offset],9))
            if key not in transf:
                tr=len(transf)+1;transf[key]=tr
                ops.geomTransf('Linear',tr,*z.tolist(),'-jntOffset',*offset,*offset)
            ef=s.get('E_factor',1)
            ops.element('elasticBeamColumn',e['id'],*e['nodes'],s['A'],E*ef,G*ef,s['J'],s['Iy'],s['Iz'],transf[key])
        else:raise ValueError(e['kind'])
    return xyz

def configure(ops, model=None):
    ops.constraints('Transformation' if model and model.get('rigid_joints') else 'Plain')
    ops.numberer('RCM');ops.system('UmfPack')
    ops.test('NormDispIncr',1e-10,20);ops.algorithm('Linear');ops.integrator('LoadControl',1.)
    ops.analysis('Static')

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',default='SERVICE_ILLUSTRATION');p.add_argument('--modes',type=int,default=6);a=p.parse_args()
    try:import openseespy.opensees as ops
    except ImportError as exc:raise SystemExit('OpenSeesPy is not installed. See README.md and the official Python-version requirements. '+str(exc))
    m=json.loads(a.model.read_text());a.output.mkdir(parents=True,exist_ok=True)
    cases=list(m['load_cases']) if a.case=='all' else [a.case]; report={'engine':'OpenSeesPy','version':ops.version(),'cases':{},'modes':[],'scope':'Linear-elastic analysis; NOT code-design approval'}
    write_json(a.output/'summary.json', report)
    for case in cases:
        if case not in m['load_cases']:raise SystemExit('Unknown load case '+case)
        xyz=build(ops,m);ops.timeSeries('Linear',1);ops.pattern('Plain',1,1)
        for ld in m['load_cases'][case]['nodal_loads']:ops.load(ld['node'],*ld['vector'])
        configure(ops,m);code=ops.analyze(1)
        if code:raise RuntimeError(f'OpenSees analysis failed: {case}, code={code}')
        disp=np.array([ops.nodeDisp(n['id']) for n in m['nodes']])
        checks=static_checks(ops,m,case,xyz)
        actions=checks.pop('joint_actions')
        report['cases'][case]={'return_code':code, **checks}
        write_json(a.output/'summary.json', report)
        if actions:
            with (a.output/(case+'_joint_actions.csv')).open('w',newline='') as f:
                w=csv.writer(f)
                w.writerow(['master','slave','master_x_m','master_y_m','master_z_m',
                            'slave_x_m','slave_y_m','slave_z_m',
                            *['slave_'+key for key in ('Fx_kN','Fy_kN','Fz_kN','Mx_kNm','My_kNm','Mz_kNm')],
                            *['master_'+key for key in ('Fx_kN','Fy_kN','Fz_kN','Mx_kNm','My_kNm','Mz_kNm')]])
                for action in actions:
                    w.writerow([action['master'],action['slave'],*xyz[action['master']],*xyz[action['slave']],
                                *action['force_on_slave_kN_kNm'],*action['force_on_master_kN_kNm']])
        with (a.output/(case+'_reactions.csv')).open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['node','Fx_kN','Fy_kN','Fz_kN','Mx_kNm','My_kNm','Mz_kNm'])
            for s in m['supports']:w.writerow([s['node'],*ops.nodeReaction(s['node'])])
        with (a.output/(case+'_nodes.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f);w.writerow(['node','x','y','z','ux_m','uy_m','uz_m','rx','ry','rz'])
            for n,d in zip(m['nodes'],disp):w.writerow([n['id'],*n['xyz'],*d])
        with (a.output/(case+'_frame_end_forces.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f);w.writerow(['element','source_name','source_guid','Ni','Vyi','Vzi','Ti','Myi','Mzi','Nj','Vyj','Vzj','Tj','Myj','Mzj'])
            for e in m['elements']:
                if e['kind']=='frame':w.writerow([e['id'],e['source_name'],e['source_guid'],*response(ops,e['id'],'localForce',12)])
        with (a.output/(case+'_shell_resultants.csv')).open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['element','source_name','source_guid','gauss_point','N11_kN_m','N22_kN_m','N12_kN_m','M11_kNm_m','M22_kNm_m','M12_kNm_m','Q1_kN_m','Q2_kN_m'])
            for e in m['elements']:
                if e['kind']=='shell':
                    for gp,v in enumerate(response(ops,e['id'],'stresses',32).reshape(4,8),1):
                        w.writerow([e['id'],e['source_name'],e['source_guid'],gp,*v])
        if not report['cases'][case]['numerical_checks_passed']:
            raise RuntimeError('Equilibrium or nodal residual check failed: '+case)
    if a.modes>0:
        build(ops,m);configure(ops,m)
        eigenvalues=ops.eigen('-genBandArpack',a.modes)
        if len(eigenvalues)!=a.modes or any(not math.isfinite(v) or v<=0 for v in eigenvalues):raise RuntimeError('Invalid modal solution')
        properties=ops.modalProperties('-return')
        write_json(a.output/'modal_properties.json',properties)
        masses={n['id']:np.zeros(6) for n in m['nodes']}
        for n in m['nodal_masses']:masses[n['node']]=np.array(n['mass'],float)
        for s in m['supports']:masses[s['node']][np.array(s['fixity'],bool)]=0
        mass_array=np.array([masses[n['id']] for n in m['nodes']])
        vectors=[]
        for i,v in enumerate(eigenvalues,1):
            phi=np.array([ops.nodeEigenvector(n['id'],i) for n in m['nodes']])
            if not np.isfinite(phi).all():raise RuntimeError('Nonfinite eigenvector')
            gm=float(np.sum(mass_array*phi*phi))
            if gm<=0:raise RuntimeError('Nonpositive generalized mass')
            influence=np.sum(mass_array[:,:3]*phi[:,:3],axis=0)
            effective=influence**2/gm
            ratios=effective/mass_array[:,:3].sum(axis=0)*100
            upstream=np.array([properties['partiMassRatios'+axis][i-1] for axis in ('MX','MY','MZ')])
            if not np.allclose(ratios,upstream,rtol=1e-7,atol=1e-8):raise RuntimeError('Modal mass cross-check failed')
            vectors.append(phi/math.sqrt(gm))
            report['modes'].append({'mode':i,'eigenvalue_rad2_s2':v,'period_s':2*math.pi/math.sqrt(v),'effective_mass_percent_xyz':ratios.tolist()})
            with (a.output/f'mode_{i:02d}_nodes.csv').open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['node','x','y','z','ux','uy','uz','rx','ry','rz'])
                for n,d in zip(m['nodes'],phi):w.writerow([n['id'],*n['xyz'],*d])
        gram=np.einsum('inj,nj,knj->ik',np.array(vectors),mass_array,np.array(vectors))
        report['modal_mass_orthogonality_max_error']=float(np.max(abs(gram-np.eye(a.modes))))
        if report['modal_mass_orthogonality_max_error']>1e-6:raise RuntimeError('Modal mass orthogonality failed')
    report['diagnostic_checks_passed']=True
    write_json(a.output/'summary.json',report);print(json.dumps(report,indent=2));ops.wipe()
if __name__=='__main__':main()
