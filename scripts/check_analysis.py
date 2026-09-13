"""Check recorded whole-model repeatability, superposition, mass and mesh results."""
import argparse
import json
from pathlib import Path
import numpy as np
from structural_ai.provenance import file_hash, write_json
from structural_ai.opensees_runner import resultant


def nodes(path):
    return np.loadtxt(path,delimiter=',',skiprows=1,encoding='utf-8-sig')


def compare(build, run, other_build, other_run):
    m = json.loads((build/'analytical_model.json').read_text())
    b = json.loads((other_build/'analytical_model.json').read_text())
    a = json.loads((run/'results/summary.json').read_text())
    s = json.loads((other_run/'results/summary.json').read_text())
    same = file_hash(build/'analytical_model.json') == file_hash(other_build/'analytical_model.json')
    totals = lambda model: {key:np.sum([r['vector'] for r in v['nodal_loads']],axis=0) for key,v in model['load_cases'].items()}
    la, lb = totals(m), totals(b)
    load_error = max(float(np.max(abs(la[k]-lb[k]))) for k in la)
    full_totals=[]
    for model in (m,b):
        xyz={n['id']:np.array(n['xyz']) for n in model['nodes']}
        full_totals.append({key:resultant(xyz,[(r['node'],r['vector']) for r in value['nodal_loads']])
                            for key,value in model['load_cases'].items()})
    moment_error=max(float(np.max(abs(full_totals[0][key][3:]-full_totals[1][key][3:]))) for key in la)
    sum_cases = ['D_SELF','D_SUPER','L_OFFICE','L_PARTITION','L_ROOF','L_STAIRS']
    if m.get('revision') in ('H03-B','H03-C'):sum_cases+=['D_PANEL','D_EQUIPMENT','L_LIFT']
    service = nodes(run/'results/SERVICE_ILLUSTRATION_nodes.csv')[:,4:]
    summed = sum(nodes(run/f'results/{k}_nodes.csv')[:,4:] for k in sum_cases)
    superposition = float(np.max(abs(service-summed)))
    mass_cases=['D_SELF','D_SUPER','L_PARTITION']+(['D_PANEL','D_EQUIPMENT'] if m.get('revision') in ('H03-B','H03-C') else [])
    weight = -sum(la[k][2] for k in mass_cases)
    mass = sum(r['mass'][0] for r in m['nodal_masses'])
    weight_error = abs(mass*m['materials']['g_m_s2']-weight)
    metrics = {}
    for case, axis in [('SERVICE_ILLUSTRATION',2),('X100_CALIBRATION',0),('Y100_CALIBRATION',1)]:
        old, new = a['cases'][case]['max_abs_translation_mm'][axis], s['cases'][case]['max_abs_translation_mm'][axis]
        metrics[case] = {'reference_mm':old,'comparison_mm':new,'relative_change':new/old-1}
    periods = [v['period_s'] for v in a['modes']]
    changes = [(v['period_s']/p-1) for p,v in zip(periods,s['modes'])]
    # A case-study screening tolerance for global diagnostics only, not a code limit.
    tolerance = 1e-8 if same else .05
    passed = (a.get('diagnostic_checks_passed') is True and s.get('diagnostic_checks_passed') is True
              and load_error<1e-6 and superposition<1e-9 and weight_error<1e-6
              and (m.get('revision')!='H03-C' or moment_error<1e-5)
              and len(periods)==len(s['modes'])==12
              and all(abs(v['relative_change'])<tolerance for v in metrics.values())
              and max(abs(v) for v in changes[:3])<tolerance)
    result = {'same_model':same,'global_diagnostic_comparison_passed':bool(passed),
              'tolerance_relative':tolerance,'loads_max_difference_kN_kNm':load_error,
              'full_position_moment_max_difference_kNm':moment_error,
              'moment_match_required':m.get('revision')=='H03-C',
              'service_superposition_max_difference_m_rad':superposition,
              'mass_ledger_difference_kN':weight_error,'total_mass_kN_s2_m':mass,
              'displacements':metrics,'period_relative_changes':changes,
              'model_counts':[[len(v['nodes']),len(v['elements'])] for v in (m,b)],
              'local_member_force_convergence':'NOT_CHECKED; concentrated connections may be singular',
              'engineering_approval':False}
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('build','run','other_build','other_run'):p.add_argument(name,type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=compare(a.build,a.run,a.other_build,a.other_run)
    write_json(a.output,result)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['global_diagnostic_comparison_passed'] else 1)
