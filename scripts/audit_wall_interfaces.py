"""Independently audit A01 wall ownership with horizontal polygon slices.

The builder partitions normal-to-wall intervals. This check instead subtracts
frame footprints and openings in horizontal layers, then checks volume and all
three first moments against actual shell sections/nodes.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union
from structural_ai.ifc_reader import Model
from structural_ai.provenance import file_hash, write_json
from structural_ai.joint_constraints import validate_constraints


def audit(path):
    model=json.loads(path.read_text());m=Model(path.parent/model['physical_ifc'])
    products={e.args[2]:e for kind in ('IFCCOLUMN','IFCBEAM','IFCWALL','IFCSLAB') for e in m.by_type(kind)}
    geometry={name:m.solid_geometry(e) for name,e in products.items()}
    walls={name:e for name,e in products.items() if e.type=='IFCWALL' and 'A01_NonstructuralPanel' not in m.psets(e)}
    holes=defaultdict(list)
    for relation in m.by_type('IFCRELVOIDSELEMENT'):
        holes[m[relation.args[4]].args[2]].append(m.solid_geometry(m[relation.args[5]]))
    owners=[]
    for name,e in products.items():
        if e.type not in ('IFCCOLUMN','IFCBEAM'):continue
        g=geometry[name];lo,hi=g['min'].copy(),g['max'].copy()
        if e.type=='IFCBEAM':
            slab=next(geometry[n] for n in ('S-2F','S-3F','S-RF') if abs(geometry[n]['max'][2]-hi[2])<1e-7)
            hi[2]-=slab['max'][2]-slab['min'][2]
        owners.append({'name':name,'guid':e.args[0],'type':e.type,'lo':lo,'hi':hi})
    xyz={n['id']:np.array(n['xyz']) for n in model['nodes']}
    links=validate_constraints(model,xyz)
    master={link['slave']:link['master'] for link in links}
    element_by_id={e['id']:e for e in model['elements']}
    node_sets={name:{n for i in value['analytical_elements'] for n in element_by_id[i]['nodes']}
               for name,value in model['mapping'].items()}
    actual=defaultdict(lambda:np.zeros(4))
    for element in model['elements']:
        if element['role']!='wall':continue
        coordinates=np.array([xyz[n] for n in element['nodes']])
        area=np.linalg.norm(np.cross(coordinates[1]-coordinates[0],coordinates[3]-coordinates[0]))
        volume=area*model['sections'][element['section']]['t']
        actual[element['source_name']]+=np.r_[volume,volume*coordinates.mean(0)]
    records=[];contacts=[]
    for name,e in walls.items():
        g=geometry[name];lo,hi=g['min'],g['max']
        cuts={float(lo[2]),float(hi[2])};relevant=[]
        for owner in owners:
            low=np.maximum(lo,owner['lo']);high=np.minimum(hi,owner['hi'])
            if np.any(high-low<=1e-8):continue
            relevant.append(owner);cuts.update((float(low[2]),float(high[2])))
            shared=sorted({master.get(n,n) for n in node_sets[name]}&
                          {master.get(n,n) for n in node_sets[owner['name']]})
            contacts.append({'wall_name':name,'wall_guid':e.args[0],
                'owner_name':owner['name'],'owner_guid':owner['guid'],'owner_type':owner['type'],
                'overlap_volume_m3':float(np.prod(high-low)),
                'overlap_bounds_m':[low.tolist(),high.tolist()],
                'direct_or_rigid_group_master_nodes':shared})
        for hole in holes[name]:
            cuts.update(float(z) for z in (hole['min'][2],hole['max'][2]) if lo[2]<z<hi[2])
        expected=np.zeros(4);gross=0.
        for z1,z2 in zip(sorted(cuts)[:-1],sorted(cuts)[1:]):
            z=(z1+z2)/2
            physical=box(*lo[:2],*hi[:2])
            voids=[box(*hole['min'][:2],*hole['max'][:2]) for hole in holes[name] if hole['min'][2]<z<hole['max'][2]]
            if voids:physical=physical.difference(unary_union(voids))
            gross+=physical.area*(z2-z1)
            footprints=[box(*o['lo'][:2],*o['hi'][:2]) for o in relevant if o['lo'][2]<z<o['hi'][2]]
            net=physical.difference(unary_union(footprints)) if footprints else physical
            if net.is_empty:continue
            volume=net.area*(z2-z1)
            expected+=np.array([volume,volume*net.centroid.x,volume*net.centroid.y,volume*z])
        error=np.abs(actual[name]-expected)
        records.append({'source_name':name,'source_guid':e.args[0],
            'gross_after_openings_m3':gross,'owned_volume_m3':float(expected[0]),
            'removed_frame_overlap_m3':gross-float(expected[0]),
            'expected_volume_and_first_moments_m3_m4':expected.tolist(),
            'actual_shell_volume_and_first_moments_m3_m4':actual[name].tolist(),
            'residual_m3_m4':error.tolist(),'passed':bool(np.max(error)<1e-7)})
    totals={kind:sum(c['overlap_volume_m3'] for c in contacts if c['owner_type']==kind)
            for kind in ('IFCCOLUMN','IFCBEAM')}
    passed=all(r['passed'] for r in records) and all(c['direct_or_rigid_group_master_nodes'] for c in contacts)
    return {'model_sha256':file_hash(path),'source_sha256':model['source_ifc_sha256'],
        'physical_ifc_sha256':file_hash(path.parent/model['physical_ifc']),
        'wall_records':records,'frame_contacts':contacts,'rigid_joint_count':len(links),
        'removed_wall_frame_overlap_m3':sum(r['removed_frame_overlap_m3'] for r in records),
        'intersection_volume_by_owner_m3':totals,
        'contacts_without_direct_kinematic_group':sum(not c['direct_or_rigid_group_master_nodes'] for c in contacts),
        'passed':bool(passed),'status':'PASS_SCOPED_OWNERSHIP_AND_KINEMATIC_MAPPING' if passed else 'FAIL',
        'scope':'Geometry/section volumes and centroids, and direct group presence; actual joint compatibility/forces require solver checks. No RC acceptance.',
        'engineering_approval':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=audit(args.model);write_json(args.output,report)
    print(json.dumps({key:value for key,value in report.items() if key not in ('wall_records','frame_contacts')},indent=2))
    raise SystemExit(0 if report['passed'] else 1)
