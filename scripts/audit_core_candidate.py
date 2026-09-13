"""Expose source wall-column overlaps and direct analytical joint coverage."""
import argparse
import json
from pathlib import Path
import numpy as np
from structural_ai.ifc_reader import Model
from structural_ai.provenance import write_json, file_hash


def audit(source, model_path):
    model=json.loads(model_path.read_text());physical=model_path.parent/model['physical_ifc']
    m=Model(physical);nodes={n['id']:np.array(n['xyz']) for n in model['nodes']}
    mappings=model['mapping'];elements={e['id']:e for e in model['elements']}
    columns=m.by_type('IFCCOLUMN');walls=[e for e in m.by_type('IFCWALL') if 'A01_NonstructuralPanel' not in m.psets(e)]
    records=[]
    def node_set(e):return {n for i in mappings[e.args[2]]['analytical_elements'] for n in elements[i]['nodes']}
    for c in columns:
        cg=m.solid_geometry(c)
        for w in walls:
            wg=m.solid_geometry(w)
            lo=np.maximum(cg['min'],wg['min']);hi=np.minimum(cg['max'],wg['max'])
            if np.any(hi-lo<=1e-8):continue
            # These actual A01 overlaps occur below/beside portals. Fail if a void intersects them.
            for relation in m.by_type('IFCRELVOIDSELEMENT'):
                if relation.args[4].id!=w.id:continue
                hole=m.solid_geometry(m[relation.args[5]])
                if np.all(np.minimum(hi,hole['max'])-np.maximum(lo,hole['min'])>1e-8):
                    raise ValueError('Wall-column overlap meets a void: full intersection review required')
            cn,wn=node_set(c),node_set(w)
            records.append({'column_name':c.args[2],'column_guid':c.args[0],
                'wall_name':w.args[2],'wall_guid':w.args[0],
                'overlap_bounds_m':[lo.tolist(),hi.tolist()],
                'gross_overlap_m3':float(np.prod(hi-lo)),
                'shared_direct_node_ids':sorted(cn&wn),
                'minimum_axis_node_distance_m':min(float(np.linalg.norm(nodes[a]-nodes[b])) for a in cn for b in wn)})
    return {'source_sha256':file_hash(source),'model_sha256':file_hash(model_path),
            'records':records,'gross_wall_column_overlap_m3':sum(r['gross_overlap_m3'] for r in records),
            'pairs_without_direct_shared_nodes':sum(not r['shared_direct_node_ids'] for r in records),
            'status':'ADOPTION_HOLD_DIRECT_JOINT_IDEALIZATION_AND_OVERLAP_OWNERSHIP' if any(not r['shared_direct_node_ids'] for r in records) else 'DIRECT_NODE_SCREEN_ONLY',
            'scope':'Physical box intersections independently checked for absence of intersecting voids; current global model connects through floor-level beams/slabs. Graph connectivity is not monolithic joint stiffness or RC reinforcement verification.',
            'engineering_approval':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('model',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=audit(a.source,a.model);write_json(a.output,report)
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
