"""Audit A01 hard-coded model choices against the unchanged source; no redesign."""
import argparse
import json
from pathlib import Path
import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from structural_ai.ifc_reader import Model
from structural_ai.provenance import file_hash, write_json


def audit(source, model):
    f=Model(source)
    m=json.loads(Path(model).read_text())
    xyz={n['id']:np.array(n['xyz']) for n in m['nodes']}
    objects={e.args[2]:e for typ in ('IFCCOLUMN','IFCBEAM','IFCWALL','IFCSLAB','IFCSTAIRFLIGHT') for e in f.by_type(typ)}
    geom={name:f.solid_geometry(e) for name,e in objects.items()}
    checks=[]
    def check(name,passed):checks.append({'check':name,'passed':bool(passed)})
    check('source_hash',file_hash(Path(source))==m['source_ifc_sha256'])
    check('all_supports_at_trial_base',all(xyz[s['node']][2]==-1.2 and s['fixity']==[1]*6 for s in m['supports']))
    check('no_ground_floor_stiffness',not any(e['source_name']=='S-1F' for e in m['elements']))
    check('source_guid_mapping',all(e['source_guid']==objects[e['source_name']].args[0] for e in m['elements'] if e['source_name'] in objects))
    check('mapping_covers_every_element',sorted(i for v in m['mapping'].values() for i in v['analytical_elements'])==sorted(e['id'] for e in m['elements']))
    check('positive_masses',all(np.isfinite(n['mass']).all() and min(n['mass'])>=0 for n in m['nodal_masses']))
    if m.get('stair_transfer_method')=='H02_RELEASED_GRAVITY_STRIPS':
        mapping=m['load_only_mapping']
        expected={name for name,obj in objects.items() if obj.type=='IFCSTAIRFLIGHT' or name.startswith('STL-')}
        check('load_only_stair_guid_and_node_mapping',set(mapping)==expected and all(
            record['ifc_guid']==objects[name].args[0] and record['receiving_nodes']
            and all(n in xyz for n in record['receiving_nodes']) for name,record in mapping.items()))
    check('frame_sections_match_source',all(np.allclose(sorted((g['max']-g['min'])[:2]),[.6,.6]) for name,g in geom.items() if objects[name].type=='IFCCOLUMN') and
          all(abs((g['max']-g['min'])[2]-.7)<1e-8 and abs(min((g['max']-g['min'])[:2])-.4)<1e-8 for name,g in geom.items() if objects[name].type=='IFCBEAM'))
    check('floor_and_wall_thickness',all(abs((g['max']-g['min'])[2]-.18)<1e-8 for name,g in geom.items() if name.startswith('S-')) and
          all(abs(min((g['max']-g['min'])[:2])-.25)<1e-8 for name,g in geom.items() if objects[name].type=='IFCWALL'))
    beams=[]
    for name,obj in objects.items():
        if obj.type!='IFCBEAM':continue
        parts=[e for e in m['elements'] if e['source_name']==name]
        ps=f.psets(obj)['A01_MainBeam']
        centres=[(geom[ps[key]]['min']+geom[ps[key]]['max'])[:2]/2 for key in ('StartColumn','EndColumn')]
        length=np.linalg.norm(centres[1]-centres[0])
        actual=sum(np.linalg.norm(xyz[e['nodes'][1]]-xyz[e['nodes'][0]]) for e in parts)
        beams.append({'source':name,'guid':obj.args[0],'span_m':float(length),'mapped_span_m':float(actual)})
        check('orthogonal_continuous_'+name,abs(length-actual)<1e-6 and
              all(np.count_nonzero(abs(xyz[e['nodes'][1]]-xyz[e['nodes'][0]])>1e-7)==1 for e in parts) and
              all(any(np.linalg.norm(xyz[n][:2]-c)<1e-7 for e in parts for n in e['nodes']) for c in centres))
    check('B2_C2_retained',all(any(np.linalg.norm(((g['min']+g['max'])/2)[:2]-[x,4.2])<1e-7 for name,g in geom.items() if objects[name].type=='IFCCOLUMN') for x in (6.,12.)))
    wall_checks=[]
    for name,obj in objects.items():
        if obj.type!='IFCWALL':continue
        g=geom[name];axis=int(np.argmin((g['max']-g['min'])[:2]));mid=(g['min'][axis]+g['max'][axis])/2
        ns={n for e in m['elements'] if e['source_name']==name for n in e['nodes']}
        error=max(abs(xyz[n][axis]-mid) for n in ns)
        wall_checks.append({'source':name,'max_midplane_error_m':float(error)})
    check('wall_midplanes_match_source',max(v['max_midplane_error_m'] for v in wall_checks)<1e-7)
    normals=[]
    for e in m['elements']:
        if e['kind']!='shell':continue
        a,b,c,d=[xyz[n] for n in e['nodes']]
        cross=np.cross(b-a,d-a);area=np.linalg.norm(cross)
        normals.append(tuple(np.round(cross/area,6)))
        if area<=0 or abs(np.dot(cross,c-a))>1e-8:raise ValueError('Invalid shell geometry')
    stairs=[{'source':name,'rough_width_m':float((g['max']-g['min'])[0]),
             'number_risers':objects[name].args[8],'riser_m':objects[name].args[10],
             'tread_m':objects[name].args[11]} for name,g in geom.items() if objects[name].type=='IFCSTAIRFLIGHT']
    landings=[{'source':name,'flight_interface_y_m':float(g['min'][1]),
               'inherited_reaction_station_y_m':9.75,
               'historical_difference_m':float(9.75-g['min'][1]),
               'current_transfer':m.get('stair_transfer_method','INHERITED_NEAREST_STATION'),
               'detail':'stair_transfer.json for current support forces; historical station is not current H02 load location'} for name,g in geom.items() if name.startswith('STL-')]
    # Sample vertical clear distance above actual tread surfaces. This excludes
    # finishes, handrails, roofs/equipment absent from the source and edge paths.
    stair_sections={name:Polygon(g['vertices'][:len(g['profile']),:][:,[1,2]])
                    for name,g in geom.items() if objects[name].type=='IFCSTAIRFLIGHT'}
    holes={}
    for rel in f.by_type('IFCRELVOIDSELEMENT'):
        host=f[rel.args[4]].args[2];g=f.solid_geometry(f[rel.args[5]])
        holes.setdefault(host,[]).append(box(*g['min'][:2],*g['max'][:2]))
    headroom=[]
    for name,section in stair_sections.items():
        g=geom[name];x=float((g['min'][0]+g['max'][0])/2);distances=[]
        for y in np.linspace(g['min'][1]+.02,g['max'][1]-.02,101):
            ray=LineString([(y,-1),(y,30)])
            tread=section.intersection(ray).bounds[3]
            overhead=[]
            for other,og in geom.items():
                if other==name or not (og['min'][0]<x<og['max'][0] and og['min'][1]<y<og['max'][1]):continue
                if any(h.contains(Point(x,y)) for h in holes.get(other,[])):continue
                bottom=float(og['min'][2])
                if other in stair_sections:
                    cut=stair_sections[other].intersection(ray)
                    if cut.is_empty:continue
                    bottom=cut.bounds[1]
                if bottom>tread+.01:overhead.append(bottom-tread)
            if overhead:distances.append(min(overhead))
        headroom.append({'source':name,'samples':101,'samples_with_overhead':len(distances),
                         'minimum_sampled_vertical_gap_m':min(distances) if distances else None,
                         'code_clearance_status':'NOT_CHECKED; centreline raw-geometry screen only'})
    return {'source_sha256':file_hash(Path(source)),'model_sha256':file_hash(Path(model)),
            'checks':checks,'all_scoped_checks_passed':all(c['passed'] for c in checks),
            'beams':beams,'wall_midplanes':wall_checks,'shell_normals':sorted(set(normals)),
            'stairs':stairs,'landing_transfer_discrepancies':landings,
            'stair_headroom_screen':headroom,
            'engineering_approval':False,'clearance_and_anchorage':'NOT_CHECKED'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('model',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=audit(a.source,a.model);write_json(a.output,result)
    print({'checks':len(result['checks']),'passed':result['all_scoped_checks_passed'],
           'landing_transfer_discrepancies':result['landing_transfer_discrepancies']})
    raise SystemExit(0 if result['all_scoped_checks_passed'] else 1)
