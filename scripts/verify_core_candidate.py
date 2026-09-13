"""Reproduce H03 candidate diagnostics without adopting its geometry.

Invoke under the host build wrapper. All subprocesses run sequentially. Each
failure and command is retained; a completed solve does not clear joint design.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
import yaml
from structural_ai.cli import load_project, received_scheme
from structural_ai.provenance import make_run, finish_run, write_json, file_hash
from structural_ai.core_revision import revise_core
from structural_ai.ifc_reader import Model
from structural_ai.model_builder import create


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=Path('project'))
    parser.add_argument('--revision',choices=('H03-B','H03-C'),default='H03-B')
    a=parser.parse_args()
    directory,project,source,config,root=load_project(a.project)
    received_source=received_scheme(directory,project)
    proposal_path=directory/project['architectural_handoff']['core_proposal']
    candidate=directory/project['architectural_handoff']['core_candidate_ifc']
    scheme_path=directory/project['inputs']['architectural_scheme']
    equipment_path=directory/'structural/design/core-interface-loads.yaml'
    proposal,scheme,equipment,cfg=[yaml.safe_load(p.read_text()) for p in (proposal_path,scheme_path,equipment_path,config)]
    run,manifest=make_run(root,project['id'],'candidate-verification')
    manifest['command']=['python','scripts/verify_core_candidate.py','--project',directory.relative_to(root).as_posix(),
                         '--revision',a.revision]
    commands=[]
    relative=lambda p:Path(p).resolve().relative_to(root).as_posix()
    def execute(label,args):
        t=time.monotonic()
        with (run/(label+'.stdout.log')).open('w') as stdout,(run/(label+'.stderr.log')).open('w') as stderr:
            proc=subprocess.run([sys.executable,*args],stdout=stdout,stderr=stderr,cwd=root)
        commands.append({'label':label,'command':['python',*args],'return_code':proc.returncode,
                         'process_elapsed_seconds':time.monotonic()-t})
        write_json(run/'commands.json',{'commands':commands})
        print(label,proc.returncode,flush=True)
        if proc.returncode:raise RuntimeError(f'{label} failed; evidence retained')
    try:
        receipt=revise_core(received_source,proposal,run/'candidate.ifc',scheme)
        write_json(run/'source-revision.json',receipt)
        if file_hash(run/'candidate.ifc')!=file_hash(candidate):
            raise ValueError('Candidate differs from the controlled source revision; do not bypass')
        execute('candidate-ifc',['scripts/audit_ifc.py',relative(candidate),'--output',relative(run/'candidate-ifc.json')])
        audit=json.loads((run/'candidate-ifc.json').read_text())
        if audit['schema_findings'] or any(not r.get('bbox_match') or not r.get('volume_match') for r in audit['products']) or any(not r['void_removes_volume'] for r in audit['voids']):
            raise ValueError('Independent candidate IFC checks failed')
        m=Model(candidate)
        pit=next(e for e in m.by_type('IFCSLAB') if e.args[2]=='S-PIT')
        trial_base=float(m.solid_geometry(pit)['min'][2])
        builds={};analyses={}
        for label,mesh,base,high in [('baseline',.75,trial_base,False),('repeat',.75,trial_base,False),
                                     ('mesh050',.5,trial_base,False),('equipment-high',.75,trial_base,True),
                                     ('base-deeper',.75,trial_base-.30,False)]:
            build=run/(label+'-build');build.mkdir()
            settings=deepcopy(cfg);settings['revision']=a.revision;settings['base']['elevation_m']=base
            settings['source_ifc']=relative(candidate)
            settings['analysis']['stair_handling']='Source-derived released H03 strips; no stiffness or reinforcement design'
            settings['loads']['unknown_excluded_loads']=['actual_lift_reactions_and_lateral_anchors','tanks','detailed_MEP','construction_loads']
            settings['mass']['source']='D_SELF + D_SUPER + L_PARTITION + D_PANEL + D_EQUIPMENT; no impact or payload mass'
            settings['limitations']=[v for v in settings['limitations'] if not v.startswith('Unknown equipment')]
            note='Synthetic equipment/roof allowances support diagnostic analysis only; actual reactions, tanks and local support design remain open.'
            if note not in settings['limitations']:settings['limitations'].append(note)
            if a.revision=='H03-C':
                settings['mesh']['wall_corner_model']='physical_midplanes_with_verified_eccentric_rigid_contacts'
                settings['loads']['classification']['lateral_calibration']='Uniform net floor-area distribution; fixed resultants across meshes; NOT wind/seismic'
                note='Rigid monolithic contacts and short joint zones omit bond slip, finite panel-zone shear flexibility and cracking; no joint reinforcement design.'
                if note not in settings['limitations']:settings['limitations'].append(note)
            e=deepcopy(equipment)
            if high:
                e['lift']['adopted_mass_multiplier']=e['lift']['mass_sensitivity_multipliers'][-1]
                e['roof']['adopted_equipment_dead_kN']=e['roof']['sensitivity_upper_kN']
            cfgpath=build/'candidate-analysis.yaml';eqpath=build/'candidate-equipment.yaml'
            cfgpath.write_text(yaml.safe_dump(settings,sort_keys=False));eqpath.write_text(yaml.safe_dump(e,sort_keys=False))
            # Record in-process builder boundaries and elapsed time separately from solver time.
            t=time.monotonic()
            import contextlib
            with (build/'build.log').open('w') as log,contextlib.redirect_stdout(log):
                create(candidate,cfgpath,build,mesh_size=mesh,architect_scheme=scheme_path,equipment_basis=eqpath)
            write_json(build/'invocation.json',{'call':'structural_ai.model_builder.create',
                'source':relative(candidate),'config':relative(cfgpath),'outdir':relative(build),
                'mesh_size':mesh,'architect_scheme':relative(scheme_path),'equipment_basis':relative(eqpath),
                'elapsed_seconds':time.monotonic()-t,'completed':True})
            if label=='baseline':
                if a.revision=='H03-C':
                    execute('connections',['scripts/audit_wall_interfaces.py',relative(build/'analytical_model.json'),
                                           '--output',relative(run/'connections.json')])
                else:
                    execute('connections',['scripts/audit_core_candidate.py',relative(candidate),relative(build/'analytical_model.json'),
                                           '--output',relative(run/'connections.json')])
            analysis=run/(label+'-analysis')
            execute(label+'-analysis',['-m','structural_ai.opensees_runner','--model',relative(build/'analytical_model.json'),
                                      '--output',relative(analysis/'results'),'--case','all','--modes','12'])
            builds[label]=relative(build);analyses[label]=relative(analysis)
            write_json(run/'run-links.json',{'builds':builds,'analyses':analyses})
        for label in ('repeat','mesh050'):
            execute(label+'-comparison',['scripts/check_analysis.py',builds['baseline'],analyses['baseline'],
                builds[label],analyses[label],'--output',relative(run/(label+'-comparison.json'))])
        execute('eigenpairs',['scripts/check_modes.py',builds['baseline']+'/analytical_model.json',
            analyses['baseline']+'/results','--output',relative(run/'eigenpairs.json')])
        execute('generated-ifc',['scripts/audit_ifc.py',builds['baseline']+f'/A01_Structural_{a.revision}_Candidate.ifc',
            '--output',relative(run/'generated-ifc.json')])
        audit=json.loads((run/'generated-ifc.json').read_text())
        if audit['schema_findings'] or any(not r.get('bbox_match') or not r.get('volume_match') for r in audit['products']) or any(not r['void_removes_volume'] for r in audit['voids']):
            raise ValueError('Generated IFC checks failed')
        finish_run(run,manifest,('COMPLETED_CANDIDATE_DIAGNOSTICS_AWAITING_ADOPTION_REVIEW' if a.revision=='H03-C'
                               else 'COMPLETED_CANDIDATE_DIAGNOSTICS_ADOPTION_HELD'),exit_code=0,
                   solver_executed=True,structural_geometry_adopted=False,
                   adoption_blocker=('Controlled source/config authority and drawing/reaction adoption review remains'
                                     if a.revision=='H03-C' else
                                     'Direct monolithic wall-column joint mapping and overlap ownership require review; current candidate uses floor-level beam/slab connections'))
    except BaseException:
        (run/'failure.txt').write_text(traceback.format_exc().replace(str(root),'<repository-root>'))
        finish_run(run,manifest,'FAILED_CANDIDATE_VERIFICATION',exit_code=1,structural_geometry_adopted=False)
        print(relative(run),flush=True)
        raise
    print(relative(run),flush=True)


if __name__=='__main__':main()
