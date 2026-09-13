"""Controlled A01 core source revision, not a general IFC importer or designer.

Writes a candidate only. Promotion requires independent geometry/converter review.
Existing product identities are retained; added products use deterministic GUIDs.
"""
from pathlib import Path
import hashlib
import math
import uuid
import numpy as np
from shapely.geometry import Polygon, box
from .ifc_reader import Model, Ref, Token, Typed, NULL
from .core_review import flights

RECEIVED_SHA256 = 'ef15b682abe8b5318365d58588a88c8150138602e4a0b4e187b5ac037d956438'


def stable_guid(name):
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$'
    value = uuid.uuid5(uuid.NAMESPACE_URL, 'structural-ai/A01/H03-B/' + name).int
    result = []
    for _ in range(22):
        result.append(alphabet[value & 63]); value >>= 6
    return ''.join(reversed(result))


def horizontal_polygon(geometry):
    """World XY footprint of the supported vertical extrusion."""
    n = len(geometry['profile'])
    if not np.allclose((geometry['vertices'][n:] - geometry['vertices'][:n])[:, :2], 0):
        raise ValueError('Expected a reviewed vertical extrusion')
    polygon = Polygon(geometry['vertices'][:n, :2])
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError('Invalid extrusion footprint')
    return polygon


def revise_core(source, proposal, output, scheme):
    source, output = Path(source), Path(output)
    if hashlib.sha256(source.read_bytes()).hexdigest() != RECEIVED_SHA256:
        raise ValueError('Core revision requires the reviewed received source, not an already extended or revised IFC')
    if proposal['revision'] != 'H03-B':
        raise ValueError('Only the explicit H03-B revision is supported')
    if output.resolve() == source.resolve():
        raise ValueError('Candidate generation must not overwrite the authoritative source')
    m = Model(source)
    products = {e.args[2]: e for typ in ('IFCCOLUMN','IFCBEAM','IFCWALL','IFCSLAB','IFCSTAIRFLIGHT','IFCOPENINGELEMENT') for e in m.by_type(typ)}
    original = {name: {'guid': e.args[0], 'kind': e.type,
                      'geometry': m.solid_geometry(e)} for name, e in products.items()}
    owner, zdir, xdir = Ref(5), Ref(6), Ref(7)
    point = lambda xyz: m.new('IFCCARTESIANPOINT', tuple(float(v) for v in xyz))
    origin = point((0,0,0))
    axis = m.new('IFCAXIS2PLACEMENT3D', origin, zdir, xdir)
    placement = m.new('IFCLOCALPLACEMENT', NULL, axis)
    added, changed = [], []
    def shape(entity, profile, at, direction=(0,0,1), reference=(1,0,0), depth=.18):
        polygon = Polygon(profile)
        if not polygon.is_valid or polygon.area <= 0 or depth <= 0:
            raise ValueError('Invalid proposed extrusion')
        curve = m.new('IFCPOLYLINE', tuple(point(p) for p in [*profile, profile[0]]))
        pr = m.new('IFCARBITRARYCLOSEDPROFILEDEF', Token('.AREA.'), NULL, curve)
        a = m.new('IFCAXIS2PLACEMENT3D', point(at), m.new('IFCDIRECTION', tuple(float(v) for v in direction)),
                  m.new('IFCDIRECTION', tuple(float(v) for v in reference)))
        solid = m.new('IFCEXTRUDEDAREASOLID', pr, a, zdir, float(depth))
        rep = m.new('IFCSHAPEREPRESENTATION', Ref(11), 'Body', 'SweptSolid', (solid,))
        ps = m.new('IFCPRODUCTDEFINITIONSHAPE', NULL, NULL, (rep,))
        prior_shape = entity.args[6]
        args = list(entity.args); args[5:7] = [placement, ps]
        args[3] = 'H03-B coordinated trial geometry; capacity, reinforcement and construction acceptance remain open.'
        entity.args = tuple(args)
        if isinstance(prior_shape, Ref):
            # ProductDefinitionShape requires at least one owning product.
            owners=[e for e in products.values() if e.args[6] == prior_shape]
            if not owners:
                for representation in m[prior_shape].args[2]:
                    del m.entities[representation.id]
                del m.entities[prior_shape.id]
        if entity.args[2] in original and entity.args[2] not in changed: changed.append(entity.args[2])
    def flat(entity, polygon, lo, hi):
        shape(entity, list(polygon.exterior.coords)[:-1], (0,0,lo), depth=hi-lo)
    def rectangle(entity, bounds, lo, hi):
        flat(entity, box(*bounds), lo, hi)
    def add(kind, name, polygon, lo, hi, container=Ref(41), subtype='.NOTDEFINED.'):
        p = m.new(kind, stable_guid(name), owner, name, 'H03-B trial geometry', NULL,
                  placement, NULL, name, Token(subtype))
        e = m[p]; products[name] = e; added.append(name)
        flat(e, polygon, lo, hi)
        if kind != 'IFCOPENINGELEMENT':
            m.new('IFCRELCONTAINEDINSPATIALSTRUCTURE', stable_guid(name+'/containment'), owner,
                  NULL, NULL, (p,), container)
        return e
    def properties(entity, name, values):
        refs = []
        for k, value in values.items():
            typ = 'IFCREAL' if isinstance(value, (int,float)) else 'IFCTEXT'
            refs.append(m.new('IFCPROPERTYSINGLEVALUE', k, NULL, Typed(typ, (value,)), NULL))
        ps = m.new('IFCPROPERTYSET', stable_guid(entity.args[2]+'/'+name), owner, name, NULL, tuple(refs))
        m.new('IFCRELDEFINESBYPROPERTIES', stable_guid(entity.args[2]+'/'+name+'/rel'), owner,
              NULL, NULL, (Ref(entity.id),), ps)

    s, v, roof = proposal['stair'], proposal['vestibule'], proposal['lift_and_roof']
    levels = {name: float(m.solid_geometry(products['S-'+name])['max'][2]) for name in ('1F','2F','3F','RF')}
    rows = flights(s, levels)
    pit_top = levels['1F'] + s['finish_vertical_build_up_m'] - scheme['lift']['pit_depth_below_lowest_finished_floor_m'] - roof['pit_floor_build_up_m']
    wall = .25
    x1 = float(original['SW-SHARED-STAIR-LIFT-1F']['geometry']['min'][0])
    x0 = x1 - 2*s['raw_flight_width_m'] - s['central_well_width_m']
    a1, b0 = x0+s['raw_flight_width_m'], x1-s['raw_flight_width_m']
    sy, ny = s['outer_south_y_m'], s['outer_north_y_m']
    wall_bounds = {
        'SW-STAIR-W': [x0-wall,sy,x0,ny], 'SW-STAIR-S':[x0,sy,x1,sy+wall],
        'SW-STAIR-N':[x0,ny-wall,x1,ny], 'SW-SHARED-STAIR-LIFT':[x1,sy,x1+wall,ny],
        'SW-LIFT-S':[9.5,4.5,11.55,4.75], 'SW-LIFT-N':[9.5,6.8,11.55,7.05],
        'SW-LIFT-E':[11.55,4.5,11.8,7.05]}
    for i, st in enumerate(('1F','2F','3F')):
        lo, hi = levels[st], levels[('2F','3F','RF')[i]]
        for prefix in wall_bounds:
            if not prefix.startswith('SW-LIFT-'):
                rectangle(products[prefix+'-'+st], wall_bounds[prefix], lo, hi)
        door = products['OPEN-STAIR-DOOR-'+st]
        rectangle(door, [x0-wall-.05,*[v['side_portal_y_m'][0]],x0+.05,v['side_portal_y_m'][1]],
                  lo, lo+v['portal_clear_height_m'])
        for rel in m.by_type('IFCRELVOIDSELEMENT'):
            if rel.args[5] == Ref(door.id):
                args = list(rel.args); args[4] = Ref(products['SW-STAIR-W-'+st].id); rel.args = tuple(args)
    # Separate cap elevations while retaining the shared wall's continuity.
    for prefix, bounds in wall_bounds.items():
        hi = roof['lift_cap_structural_top_z_m'] if prefix.startswith('SW-LIFT-') else roof['stair_cap_structural_top_z_m']
        add('IFCWALL', prefix+'-RF', box(*bounds), levels['RF'], hi, subtype='.SHEAR.')
        # Below-grade core stems are trial geometry, not a basement or footing design.
        e = add('IFCWALL', prefix+'-SUBGRADE', box(*bounds), pit_top, 0., Ref(29), '.SHEAR.')
        properties(e, 'A01_TrialSubgrade', {'Role':'Trial core stem to pit slab top; not a designed footing or ground restraint'})
    rd = add('IFCOPENINGELEMENT','OPEN-STAIR-DOOR-RF',box(roof['roof_door_rough_x_m'][0],sy-.05,roof['roof_door_rough_x_m'][1],sy+wall+.05),
             levels['RF'], levels['RF']+2.30, subtype='.OPENING.')
    m.new('IFCRELVOIDSELEMENT',stable_guid('roof-door-void'),owner,NULL,NULL,Ref(products['SW-STAIR-S-RF'].id),Ref(rd.id))
    for name, bounds, top, thick in (
        ('S-STAIR-CAP',[x0-wall,sy,x1+wall,ny],roof['stair_cap_structural_top_z_m'],roof['cap_trial_thickness_m']),
        ('S-LIFT-CAP',[x1,4.5,11.8,7.05],roof['lift_cap_structural_top_z_m'],roof['cap_trial_thickness_m']),
        ('S-PIT',[x1,4.5,11.8,7.05],pit_top,roof['pit_base_trial_thickness_m'])):
        e=add('IFCSLAB',name,box(*bounds),top-thick,top,Ref(41) if top>0 else Ref(29),'.ROOF.' if top>0 else '.BASESLAB.')
        properties(e,'A01_CoreSlab',{'Thickness_m':thick,'Role':'Trial cap or pit plate; strength and foundation acceptance not established'})
    for i,row in enumerate(rows):
        st, upper = row['storey'], row['upper']
        mid = row['mid_ffl_m']-s['finish_vertical_build_up_m']
        landing = Polygon([(x0,row['a_end_y_m']),(a1,row['a_end_y_m']),
                           (a1,row['b_start_y_m']),(x1,row['b_start_y_m']),
                           (x1,ny-wall),(x0,ny-wall)])
        flat(products['STL-'+st+'-MID'],landing,mid-s['nominal_landing_thickness_m'],mid)
        for letter, start, z, n, sign, extrude_x in (
            ('A',row['a_start_y_m'],levels[st],row['a_risers'],1,x0),
            ('B',row['b_start_y_m'],mid,row['b_risers'],-1,x1)):
            r,t=row['riser_m'],row['tread_m'];run=(n-1)*t
            profile=[(0.,0.)]
            for k in range(n):
                profile.append((k*t,(k+1)*r))
                if k<n-1:profile.append(((k+1)*t,(k+1)*r))
            bearing=s['upper_bearing_length_m'];vertical_waist=s['nominal_waist_normal_thickness_m']*math.sqrt(1+(r/t)**2)
            profile.extend([(run+bearing,n*r),(run+bearing,(n-1)*r-vertical_waist),
                            (run,(n-1)*r-vertical_waist),(0.,-vertical_waist)])
            e=products['STF-'+st+'-'+letter]
            shape(e,profile,(extrude_x,start,z),(sign,0,0),(0,sign,0),s['raw_flight_width_m'])
            args=list(e.args);args[8:12]=[n,n-1,r,t];e.args=tuple(args)
            for rel in m.by_type('IFCRELDEFINESBYPROPERTIES'):
                if Ref(e.id) in rel.args[4] and m[rel.args[5]].args[2]=='A01_StairFlight':
                    replacements={'RoughWidth_m':s['raw_flight_width_m'],
                                  'WaistThickness_m':s['nominal_waist_normal_thickness_m'],
                                  'HandrailAndFinishAllowanceTotal_m':scheme['stair']['wall_finish_m']+scheme['stair']['handrail_wall_gap_m']+scheme['stair']['handrail_diameter_m']}
                    for ref in m[rel.args[5]].args[4]:
                        prop=m[ref]
                        if prop.args[0] in replacements:
                            pa=list(prop.args);pa[2]=Typed('IFCREAL',(replacements[pa[0]],));prop.args=tuple(pa)
            properties(e,'A01_H03_Stair',{'WaistThickness_m':s['nominal_waist_normal_thickness_m'],
                'RawWidth_m':s['raw_flight_width_m'],'LowerSupportY_m':start,'UpperSupportY_m':start+sign*run,
                'LowerSupportZ_m':z,'UpperSupportZ_m':z+n*r,'UpperBearingLength_m':bearing})
        a_start=rows[i+1]['a_start_y_m'] if i<2 else row['a_start_y_m']
        by=row['b_end_y_m']; high=ny-wall
        hole=Polygon([(x0,a_start),(a1,a_start),(a1,by),(x1,by),(x1,high),(x0,high)])
        # Remove collinear duplicate vertices for the RF equal-edge case.
        hole=hole.buffer(0)
        flat(products['OPEN-STAIR-'+upper],hole,levels[upper]-.23,levels[upper]+.05)
    # Light enclosure panels own gravity/finish dimensions but add no shear-wall stiffness.
    for st,next_st,container in [('1F','2F',Ref(29)),('2F','3F',Ref(33)),('3F','RF',Ref(37))]:
        lo,hi=levels[st],levels[next_st]-.18
        vx0,vy0,vx1,vy1=v['outer_bounds_m'];vx1=x0
        for suffix,bounds in [('W',[vx0,vy0,vx0+.25,vy1]),('S',[vx0+.25,vy0,x0-wall,vy0+.25]),('N',[vx0+.25,vy1-.25,x0-wall,vy1])]:
            e=add('IFCWALL','NW-VEST-'+suffix+'-'+st,box(*bounds),lo,hi,container,'.PARTITIONING.')
            properties(e,'A01_NonstructuralPanel',{'Role':'LOAD_ONLY_PANEL','FaceWeight_kN_m2':v['panel_face_weight_kN_m2'],
                'Basis':'Synthetic permanent allowance; one-hour approved assembly specified, not vendor certified. No infill stiffness.'})
            if suffix=='W':
                hole=add('IFCOPENINGELEMENT','OPEN-VEST-DOOR-'+st,box(vx0-.05,v['door_rough_y_m'][0],vx0+.30,v['door_rough_y_m'][1]),lo,lo+2.30,container,'.OPENING.')
                m.new('IFCRELVOIDSELEMENT',stable_guid(hole.args[2]+'/void'),owner,NULL,NULL,Ref(e.id),Ref(hole.id))
    # Correct the received EXPRESS condition: absent LastModifiedDate requires NOCHANGE/NOTDEFINED.
    args=list(m[5].args);args[3]=Token('.NOCHANGE.');m[5].args=tuple(args)
    args=list(m[17].args);args[2:4]=['A01 Structural H03-B','Coordinated candidate; analysis/design gates recorded separately; NOT FOR CONSTRUCTION'];m[17].args=tuple(args)
    args=list(m[25].args);args[3]='RC frame and shared stair/lift core, coordinated H03-B trial geometry; not construction approved';m[25].args=tuple(args)
    args=list(m[3145].args);args[2]='A01_R05_HistoricalDesignStatus';m[3145].args=tuple(args)
    for name in added:
        if products[name].type!='IFCOPENINGELEMENT' and not name.startswith('NW-'):
            m.new('IFCRELASSOCIATESMATERIAL',stable_guid(name+'/RC'),owner,NULL,NULL,(Ref(products[name].id),),Ref(45))
    header="ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('A01 H03-B coordinated trial geometry; NOT FOR CONSTRUCTION'),'2;1');\nFILE_NAME('structural.ifc','2026-09-13T00:00:00',('A01 research project'),('Simulated design roles'),'structural-ai core revision','H03-B','');\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
    m.validate_refs();m.write(output,header)
    for name,entry in original.items():
        if entry['kind'] in ('IFCCOLUMN','IFCBEAM'):
            g=m.solid_geometry(products[name])
            if products[name].args[0]!=entry['guid'] or not np.allclose(g['vertices'],entry['geometry']['vertices'],atol=1e-10):
                raise ValueError('The main frame changed during core revision')
    return {'source_before_sha256':RECEIVED_SHA256,'source_after_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'retained_product_guids':{name:entry['guid'] for name,entry in original.items()},
            'changed_geometry_names':changed,'added_product_guids':{name:products[name].args[0] for name in added},
            'main_frame_unchanged':True,'adopted':False,'engineering_approval':False}


if __name__ == '__main__':
    import argparse
    import json
    import yaml
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--proposal',type=Path,required=True)
    parser.add_argument('--scheme',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=revise_core(args.source,yaml.safe_load(args.proposal.read_text()),args.output,yaml.safe_load(args.scheme.read_text()))
    report['proposal_sha256']=hashlib.sha256(args.proposal.read_bytes()).hexdigest()
    report['scheme_sha256']=hashlib.sha256(args.scheme.read_bytes()).hexdigest()
    args.output.with_suffix('.revision.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'candidate':args.output.name,'sha256':report['source_after_sha256'],'adopted':False}))
