"""Summarize recorded candidate variants, full resultants and trial reactions."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from structural_ai.opensees_runner import resultant
from structural_ai.provenance import write_json, file_hash


def summarize(run, output):
    manifest=json.loads((run/'manifest.json').read_text())
    if not manifest['status'].startswith('COMPLETED_CANDIDATE_DIAGNOSTICS'):
        raise ValueError('Only completed diagnostics may be summarized')
    for name,digest in manifest['output_sha256'].items():
        if file_hash(run/name)!=digest:
            raise ValueError('Verification evidence changed: '+name)
    links=json.loads((run/'run-links.json').read_text())
    labels=list(links['builds'])
    models={k:json.loads((Path(v)/'analytical_model.json').read_text()) for k,v in links['builds'].items()}
    summaries={k:json.loads((Path(v)/'results/summary.json').read_text()) for k,v in links['analyses'].items()}
    totals={}
    rows=[]
    for label in labels:
        m,s=models[label],summaries[label]
        xyz={n['id']:np.array(n['xyz']) for n in m['nodes']}
        totals[label]={k:resultant(xyz,[(v['node'],v['vector']) for v in case['nodal_loads']]) for k,case in m['load_cases'].items()}
        row={'variant':label,'model_sha256':file_hash(Path(links['builds'][label])/'analytical_model.json'),
             'base_m':m['base_elevation_m'],'nodes':len(m['nodes']),'elements':len(m['elements']),
             'service_gravity_kN':-totals[label]['SERVICE_ILLUSTRATION'][2],
             'service_vertical_mm':s['cases']['SERVICE_ILLUSTRATION']['max_abs_translation_mm'][2],
             'x100_mm':s['cases']['X100_CALIBRATION']['max_abs_translation_mm'][0],
             'y100_mm':s['cases']['Y100_CALIBRATION']['max_abs_translation_mm'][1],
             'mass_kN_s2_m':sum(n['mass'][0] for n in m['nodal_masses']),
             'period_1_s':s['modes'][0]['period_s'],'period_2_s':s['modes'][1]['period_s'],'period_3_s':s['modes'][2]['period_s'],
             'static_case_count':len(s['cases']),'mode_count':len(s['modes']),
             'all_solver_diagnostics_passed':s['diagnostic_checks_passed']}
        rows.append(row)
    mesh_delta={k:(totals['mesh050'][k]-v).tolist() for k,v in totals['baseline'].items()}
    fields=('service_gravity_kN','service_vertical_mm','x100_mm','y100_mm','mass_kN_s2_m','period_1_s','period_2_s','period_3_s')
    comparison={r['variant']:{k:r[k]/rows[0][k]-1 for k in fields} for r in rows[1:]}
    baseline=summaries['baseline'];limits={}
    for k,c in baseline['cases'].items():
        limits[k]={'force_residual_max_kN':max(abs(x) for x in c['equilibrium_residual_kN_kNm'][:3]),
                   'moment_residual_max_kNm':max(abs(x) for x in c['equilibrium_residual_kN_kNm'][3:]),
                   'nodal_residual_max_kN_kNm':c['nodal_residual_max_kN_kNm'],
                   'rigid_joint_compatibility_max_m_rad':c.get('rigid_joint_compatibility_max_m_rad')}
    corrected=models['baseline']['revision']=='H03-C'
    record={'run':run.as_posix(),'variants':rows,'relative_changes_from_baseline':comparison,
            'baseline_equilibrium':limits,'mesh_full_resultant_deltas_kN_kNm':mesh_delta,
            'baseline_12_mode_effective_mass_sum_percent_xyz':np.sum([v['effective_mass_percent_xyz'] for v in baseline['modes']],axis=0).tolist(),
            'base_reactions_note':'Unfactored candidate fixed-base nodal reactions, not foundation design loads or capacity acceptance.',
            'adoption_status':('VERIFIED_DIAGNOSTICS_SEE_CONTROLLED_ADOPTION_RECEIPT' if corrected else
                               'HELD_DIRECT_JOINT_IDEALIZATION_AND_OVERLAP_OWNERSHIP'),
            'engineering_approval':False}
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/'candidate-diagnostics.json',record)
    with (output/'candidate-variants.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    # Join trial reactions to positions and source GUIDs for later foundation input review.
    source=Path(links['analyses']['baseline'])/'results/SERVICE_ILLUSTRATION_reactions.csv'
    target=output/'candidate-trial-reactions.csv'
    m=models['baseline'];xyz={n['id']:n['xyz'] for n in m['nodes']};attached={}
    for element in m['elements']:
        for n in element['nodes']:attached.setdefault(n,set()).add((element['source_name'],element['source_guid']))
    with source.open(newline='',encoding='utf-8-sig') as f:reactions=list(csv.DictReader(f))
    for row in reactions:
        n=int(row['node']);row.update(dict(zip(('x_m','y_m','z_m'),xyz[n])))
        row['source_names']=';'.join(name for name,guid in sorted(attached[n]))
        row['source_guids']=';'.join(guid for name,guid in sorted(attached[n]))
        row['status']=('H03_C_UNFACTORED_DIAGNOSTIC_FIXED_BASE_NOT_FOUNDATION_DESIGN' if corrected else
                       'UNADOPTED_UNFACTORED_TRIAL_FIXED_BASE_NOT_FOUNDATION_DESIGN')
    with target.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(reactions[0]));writer.writeheader();writer.writerows(reactions)
    write_json(output/'reaction-provenance.json',{'source':source.as_posix(),'source_sha256':file_hash(source),
        'derived_table_sha256':file_hash(target),'model_sha256':rows[0]['model_sha256'],
        'status':('H03_C_UNFACTORED_DIAGNOSTIC_FIXED_BASE_NOT_FOUNDATION_DESIGN' if corrected else
                  'UNADOPTED_UNFACTORED_FIXED_BASE_CANDIDATE_NOT_FOUNDATION_DESIGN')})
    print(json.dumps({'variants':len(rows),'static_cases':sum(r['static_case_count'] for r in rows),
                      'adoption':record['adoption_status']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();summarize(a.run,a.output)
