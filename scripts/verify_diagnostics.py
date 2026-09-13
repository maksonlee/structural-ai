"""Reproduce A01 diagnostic evidence sequentially (invoke under host build limits)."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import yaml

from structural_ai.provenance import make_run, finish_run, write_json
from structural_ai.cli import load_project


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,default=Path('project'))
    a=p.parse_args()
    _, config, source, analysis, root=load_project(a.project)
    if yaml.safe_load(analysis.read_text()).get('revision') in ('H03-B','H03-C'):
        raise ValueError('This historical verifier is for H02/R06. Use scripts/verify_core_candidate.py --project project --revision H03-C for the current core.')
    source_path=source.relative_to(root).as_posix()
    project=a.project.resolve().relative_to(root).as_posix()
    run, manifest=make_run(root,config['id'],'verification')
    manifest['command']=['python','scripts/verify_diagnostics.py','--project',project]
    records=[]

    def execute(label, arguments):
        start=datetime.now(timezone.utc).isoformat()
        t=time.monotonic()
        with (run/(label+'.stdout.log')).open('w') as stdout,(run/(label+'.stderr.log')).open('w') as stderr:
            process=subprocess.run([sys.executable,*arguments],cwd=root,stdout=stdout,stderr=stderr)
        records.append({'label':label,'command':['python',*arguments],'started_at_utc':start,
                        'elapsed_seconds':time.monotonic()-t,'return_code':process.returncode})
        write_json(run/'commands.json',{'commands':records})
        print(label,process.returncode,flush=True)
        if process.returncode:raise RuntimeError('Failed '+label+'; logs retained')
        return (run/(label+'.stdout.log')).read_text().strip()

    def relative(path):return Path(path).resolve().relative_to(root).as_posix()
    try:
        execute('solver-identity',['-c','import openseespy.opensees as ops; print(ops.version())'])
        execute('tests',['-m','unittest','discover','-s','tests','-v'])
        execute('validate',['-m','structural_ai','validate','--project',project])
        builds=[];analyses=[]
        for label,extra in [('baseline',[]),('repeat',[]),('mesh050',['--mesh-size','0.5'])]:
            build=relative(execute(label+'-build',['-m','structural_ai','build','--project',project,*extra]))
            analysis=relative(execute(label+'-analysis',['-m','structural_ai','analyze','--project',project,
                            '--model',build+'/analytical_model.json','--case','all','--modes','12']))
            builds.append(build);analyses.append(analysis)
        write_json(run/'run_links.json',{'builds':builds,'analyses':analyses})
        execute('input-signature',['scripts/check_input_signature.py',builds[0]+'/analytical_model.json'])
        execute('mapping',['scripts/audit_mapping.py',source_path,
                           builds[0]+'/analytical_model.json','--output',relative(run/'mapping.json')])
        for i,label in [(1,'repeatability'),(2,'mesh-sensitivity')]:
            execute(label,['scripts/check_analysis.py',builds[0],analyses[0],builds[i],analyses[i],
                           '--output',relative(run/(label+'.json'))])
        execute('eigenpairs',['scripts/check_modes.py',builds[0]+'/analytical_model.json',analyses[0]+'/results',
                             '--output',relative(run/'eigenpairs.json')])
        for label,path in [('source-ifc',source_path),
                           ('generated-ifc',builds[0]+'/A01_Structural_R06_AnalysisReady.ifc')]:
            execute(label,['scripts/audit_ifc.py',path,'--output',relative(run/(label+'.json'))])
        schema_pass=all(not json.loads((run/(label+'.json')).read_text())['schema_findings']
                        for label in ('source-ifc','generated-ifc'))
        finish_run(run,manifest,'COMPLETED_SCOPED_DIAGNOSTICS',exit_code=0,
                   engineering_approval=False,full_ifc_schema_pass=schema_pass)
    except Exception:
        finish_run(run,manifest,'FAILED',exit_code=1)
        print(relative(run),flush=True)
        raise
    print(relative(run),flush=True)


if __name__=='__main__':main()
