"""A01 architectural core proposal; does not mutate IFC or run structural analysis."""
from __future__ import annotations

import math
import json
from pathlib import Path
import traceback

import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union
import yaml

from .coordination import read_geometry, Sheet
from .provenance import make_run, finish_run, write_json, file_hash


def sector(center, radius, start_degrees, end_degrees):
    """Inscribed sector for drawing. Clearance acceptance uses exact circle bounds."""
    if radius <= 0 or not np.isfinite([*center, radius]).all():
        raise ValueError('Positive finite sector required')
    points = [[center[0]+radius*math.cos(t), center[1]+radius*math.sin(t)]
              for t in np.linspace(math.radians(start_degrees), math.radians(end_degrees), 181)]
    return Polygon([center, *points, center])


def circle_gap(a, ra, b, rb):
    """Exact separating distance of full bounding discs (conservative for arcs)."""
    if min(ra, rb) <= 0 or not np.isfinite([*a, *b, ra, rb]).all():
        raise ValueError('Invalid circle envelope')
    return math.dist(a, b)-ra-rb


def flights(stair, levels):
    """Finished nosing coordinates with a full tread setback at each rising turn."""
    names = ['1F', '2F', '3F', 'RF']
    counts = stair['risers_by_storey']
    if len(counts) != 3 or any(len(p) != 2 or any(type(n) is not int or n < 2 for n in p) for p in counts):
        raise ValueError('Three pairs of integer flight riser counts required')
    heights = [levels[b]-levels[a] for a, b in zip(names, names[1:])]
    rises = [h/sum(n) for h, n in zip(heights, counts)]
    if max(rises)-min(rises) > 1e-10 or min(rises) <= 0:
        raise ValueError('Proposed riser counts do not preserve uniform rises and source levels')
    r, t = rises[0], stair['tread_m']
    if not (r <= .16 and t >= .26 and .55 <= 2*r+t <= .65):
        raise ValueError('Proposed finished R/T violates the selected accessibility screen')
    start = stair['first_up_nosing_y_m']
    finish = stair['finish_vertical_build_up_m']
    result = []
    for i, (a, b) in enumerate(zip(names, names[1:])):
        na, nb = counts[i]
        mid = levels[a]+na*r+finish
        a_end = start+(na-1)*t
        b_start = a_end-t
        b_end = b_start-(nb-1)*t
        result.append({'storey': a, 'upper': b, 'riser_m': r, 'tread_m': t,
                       'a_risers': na, 'b_risers': nb, 'a_start_y_m': start,
                       'a_end_y_m': a_end, 'b_start_y_m': b_start, 'b_end_y_m': b_end,
                       'lower_ffl_m': levels[a]+finish, 'mid_ffl_m': mid,
                       'upper_ffl_m': levels[b]+finish, 'mid_setback_m': a_end-b_start,
                       'next_floor_setback_m': t})
        start = b_end+t
    return result


def core_geometry(proposal, objects):
    west, shared = objects['SW-STAIR-W-1F'], objects['SW-SHARED-STAIR-LIFT-1F']
    thickness = west['max'][0]-west['min'][0]
    south, north = proposal['stair']['outer_south_y_m'], proposal['stair']['outer_north_y_m']
    lo, hi = west['min'][0], shared['max'][0]
    inner = box(west['max'][0], south+thickness, shared['min'][0], north-thickness)
    outer = box(lo, south, hi, north)
    x0, _, x1, _ = inner.bounds
    a1 = objects['STF-1F-A']['max'][0]
    b0 = objects['STF-1F-B']['min'][0]
    return {'inner': inner, 'outer': outer, 'wall': outer.difference(inner),
            'x': (x0, a1, b0, x1), 'thickness': thickness}


def landing_polygon(row, geometry):
    x0, a1, _, x1 = geometry['x']
    north = geometry['inner'].bounds[3]
    return Polygon([(x0,row['a_end_y_m']), (a1,row['a_end_y_m']),
                    (a1,row['b_start_y_m']), (x1,row['b_start_y_m']),
                    (x1,north), (x0,north)])


def proposal_headroom(rows, geometry, proposal, levels, objects):
    """Sample finished treads against explicit proposed soffit envelopes.

    Flight soffits conservatively follow the lower-riser pitch line minus the
    normal waist and finish. This is not an IFC intersection or final stair RC
    profile. Full source beams, proposed landings/floors/cap are checked as well.
    """
    x0, a1, b0, x1 = geometry['x']
    finish = proposal['stair']['finish_vertical_build_up_m']
    waist = proposal['stair']['nominal_waist_normal_thickness_m']
    thickness = proposal['stair']['nominal_landing_thickness_m']
    surfaces, samples = [], []
    for row in rows:
        r,t = row['riser_m'],row['tread_m']
        for letter,lo,hi,start,end,base,n,direction in (
            ('A',x0,a1,row['a_start_y_m'],row['a_end_y_m'],row['lower_ffl_m'],row['a_risers'],1),
            ('B',b0,x1,row['b_start_y_m'],row['b_end_y_m'],row['mid_ffl_m'],row['b_risers'],-1)):
            footprint=box(lo,min(start,end),hi,max(start,end))
            # Capture constants now; do not close over the next flight's loop values.
            def soffit(y, base=base, start=start, direction=direction, r=r, t=t):
                return base-finish+direction*(y-start)*r/t-waist*math.sqrt(1+(r/t)**2)
            surfaces.append((row['storey']+'-'+letter,footprint,soffit))
            for k in range(n-1):
                for u in (0.01,t-.01):
                    y=start+direction*(k*t+u)
                    for x in (lo+.1,(lo+hi)/2,hi-.1):
                        samples.append((row['storey']+'-'+letter,x,y,base+(k+1)*r))
        z=row['mid_ffl_m']-finish-thickness
        surfaces.append((row['storey']+'-landing',landing_polygon(row,geometry),lambda y,z=z:z))
    for i,lv in enumerate(('2F','3F','RF')):
        incoming=rows[i]
        a_start=rows[i+1]['a_start_y_m'] if i<2 else incoming['a_start_y_m']
        holes=unary_union([box(x0,a_start,a1,geometry['inner'].bounds[3]),
                           box(a1,min(a_start,incoming['b_end_y_m']),x1,geometry['inner'].bounds[3])])
        z=levels[lv]-.18
        surfaces.append((lv+'-floor',box(0,0,18,12).difference(holes),lambda y,z=z:z))
    for name,obj in objects.items():
        if obj['kind']=='IFCBEAM':
            z=obj['min'][2]
            surfaces.append((name,box(*obj['min'][:2],*obj['max'][:2]),lambda y,z=z:z))
    roof=proposal['lift_and_roof']
    z=roof['stair_cap_structural_top_z_m']-roof['cap_trial_thickness_m']
    surfaces.append(('proposed-stair-cap',geometry['outer'],lambda y,z=z:z))
    findings=[]
    for name,x,y,z in samples:
        above=[(soffit(y)-z,label) for label,footprint,soffit in surfaces
               if footprint.covers(Point(x,y)) and soffit(y)>z+1e-7]
        if not above:
            raise ValueError('Proposed tread has no defined overhead envelope')
        distance,label=min(above)
        findings.append({'flight':name,'xyz_m':[x,y,z],'headroom_m':distance,'overhead':label})
    return {'method':'Sampled proposed envelope screen; not final IFC/finished route validation',
            'sample_count':len(findings),'minimum':min(findings,key=lambda x:x['headroom_m']),
            'below_1_90_m':sum(x['headroom_m']<1.90 for x in findings),
            'samples':findings}


def portal_clearance(proposal, objects, finish):
    """Actual portal throat after column intrusions; no nearest-solid assumptions."""
    west=objects['SW-STAIR-W-1F']
    y0,y1=proposal['vestibule']['side_portal_y_m']
    throat=box(west['min'][0],y0,west['max'][0],y1)
    intervals=[(y0,y1)]; conflicts=[]
    for name,o in objects.items():
        if o['kind']!='IFCCOLUMN' or abs(o['min'][2])>1e-8:continue
        overlap=throat.intersection(box(*o['min'][:2],*o['max'][:2]))
        if overlap.area<1e-10:continue
        low,high=overlap.bounds[1],overlap.bounds[3]
        remaining=[]
        for a,b in intervals:
            if low>=b or high<=a:remaining.append((a,b))
            else:
                if a<low:remaining.append((a,low))
                if high<b:remaining.append((high,b))
        intervals=remaining
        conflicts.append({'source_name':name,'source_guid':o['guid'],
                          'throat_intersection_bounds_m':list(overlap.bounds),'area_m2':overlap.area})
    clear=max((b-a for a,b in intervals),default=0.)-2*finish
    return {'rough_width_m':y1-y0,'finished_unobstructed_width_m':max(0.,clear),
            'remaining_intervals_y_m':intervals,'column_conflicts':conflicts,
            'scope':'Plan throat screen at occupied floor levels; not all-point egress acceptance'}


def evaluate(proposal, load_basis, scheme, objects, levels, gravity, received_objects=None):
    geom=core_geometry(proposal,objects)
    rows=flights(proposal['stair'],levels)
    x0,a1,b0,x1=geom['x'];south,north=geom['inner'].bounds[1::2]
    v=proposal['vestibule'];s=proposal['stair'];roof=proposal['lift_and_roof']
    hinge=v['door_hinge_m'];leaf=np.diff(v['door_rough_y_m'])[0]-2*v['door_frame_each_side_m']
    radius=s['turning_envelope_radius_m'];centre=(x0+x1)/2
    # Accept only exact full-disc separation, not a polygon/chord approximation.
    gap=min(circle_gap(hinge,leaf,[centre,row['b_end_y_m']],radius) for row in rows)
    door_bounds=box(hinge[0],hinge[1],hinge[0]+leaf,hinge[1]+leaf)
    columns=[box(*o['min'][:2],*o['max'][:2]) for o in objects.values()
             if o['kind']=='IFCCOLUMN' and abs(o['min'][2])<1e-8]
    approach=box(*v['protected_approach_bounds_m'])
    vestibule=box(*v['outer_bounds_m'])
    door_clear=leaf-v['door_leaf_thickness_m']
    portal_clear=np.diff(v['side_portal_y_m'])[0]-2*scheme['stair']['wall_finish_m']
    landing_front=min(row['b_end_y_m']-south for row in rows)
    landing_rear=min(north-row['a_end_y_m'] for row in rows)
    received=received_objects or objects
    old_west=received['SW-STAIR-W-1F'];old_north=received['SW-STAIR-N-1F']
    old_south=received['SW-STAIR-S-1F']
    old_outer=box(old_west['min'][0],old_south['min'][1],objects['SW-SHARED-STAIR-LIFT-1F']['max'][0],old_north['max'][1])
    old_depth=old_north['min'][1]-old_south['max'][1]
    r=rows[0]['riser_m'];minimum_t=max(.26,.55-2*r)
    minimum_depth=(rows[0]['a_risers']-1)*minimum_t+minimum_t+2*(a1-x0)
    width=a1-x0
    stair_area=sum(width*((q['a_risers']-1)+(q['b_risers']-1))*q['tread_m']+landing_polygon(q,geom).area for q in rows)
    west_room=next(x for x in scheme['spaces'] if x['id']=='W1')
    planning_loss=box(*west_room['bounds_m']).intersection(unary_union([geom['outer'],vestibule,approach])).area
    lift=scheme['lift'];highest=levels['3F']+s['finish_vertical_build_up_m']
    pit_finished=levels['1F']+s['finish_vertical_build_up_m']-lift['pit_depth_below_lowest_finished_floor_m']
    cap_t=roof['cap_trial_thickness_m']
    lb=load_basis['lift'];car=lb['assumed_car_and_sling_kg'];payload=lb['rated_payload_kg']
    if payload!=700 or payload<=0 or min(car,lb['assumed_machine_rails_ropes_and_miscellaneous_kg'])<=0:
        raise ValueError('Review the candidate-specific equipment envelope')
    counter=car+lb['assumed_counterweight_balance_fraction']*payload
    permanent=car+counter+lb['assumed_machine_rails_ropes_and_miscellaneous_kg']
    equipment=[{'equipment_mass_multiplier':f,'permanent_kN':permanent*f*gravity/1000,
                'loaded_static_kN':(permanent*f+payload)*gravity/1000,
                'alternative_head_or_buffer_envelope_kN':(permanent*f+payload)*gravity/1000*lb['vertical_envelope_factor']}
               for f in lb['mass_sensitivity_multipliers']]
    baseline_hinge=[7.30,4.76]
    baseline_turn=[centre,objects['OPEN-STAIR-2F']['min'][1]]
    baseline_overlap=sector(baseline_hinge,1.10,0,90).intersection(sector(baseline_turn,radius,180,360)).area
    interfaces=[]
    for name,o in objects.items():
        selected=(o['kind']=='IFCCOLUMN' and abs(o['min'][2])<1e-8) or (
            o['kind']=='IFCBEAM' and abs(o['max'][2]-levels['2F'])<1e-8)
        if selected:
            area=geom['wall'].intersection(box(*o['min'][:2],*o['max'][:2])).area
            if area>1e-8:
                interfaces.append({'source_name':name,'source_guid':o['guid'],'wall_plan_intersection_m2':area,
                                   'status':'STRUCTURAL_JOINT_AND_VOLUME_OWNERSHIP_REVIEW_REQUIRED'})
    checks=[]
    def check(key,clause,value,criterion,passed,coverage):
        checks.append({'id':key,'clause':clause,'location':'Proposed core; 1F-3F/RF as stated',
                       'combination':'NOT_APPLICABLE_GEOMETRIC_SCREEN','value':value,'criterion':criterion,
                       'status':'PASS_PROPOSED_DIMENSIONS_ONLY' if passed else 'HOLD', 'coverage':coverage})
    check('H03-C01','Accessibility 304.1',{'riser_m':r,'tread_m':s['tread_m'],'2R_plus_T_m':2*r+s['tread_m']},
          'Uniform finished risers and treads; R <= 0.16, T >= 0.26, 0.55 <= 2R+T <= 0.65',True,'No field tolerance or construction acceptance')
    check('H03-C02','Accessibility 303.2',{'mid_and_next_floor_setback_m':s['tread_m']},
          'Each rising flight retreats at least one tread',all(q['mid_setback_m']>=s['tread_m']-1e-9 for q in rows),
          'Stepped landing/opening edges required; central handrail fabrication/anchorage still pending')
    check('H03-C03','Design/construction Articles 33(4), 34',{'minimum_front_m':landing_front,'minimum_rear_m':landing_rear,'flight_width_m':width},
          'Landing depth >= raw flight width; conservative turn radius contained',min(landing_front,landing_rear)>=radius+s['dimensional_allowance_m'],
          'Finished surfaces and rail intrusions checked separately; full route not accepted')
    check('H03-C04','Design/construction Articles 33(4), 76, 97',{'full_disc_separation_m':gap,'nominal_door_clear_m':door_clear,'leaf_area_m2':leaf*v['door_leaf_height_m']},
          'Positive exact disc separation with 20 mm margin; door clear >= 0.90 m',gap>=.02 and door_clear>=.90 and leaf*v['door_leaf_height_m']<=3,
          '2F/3F inward entry only; ground outward swing and certified assemblies remain separate holds; RF has a different south door')
    portal=portal_clearance(proposal,objects,scheme['stair']['wall_finish_m'])
    check('H03-C05','Design/construction Article 97; project 1.20 m passage target',{'portal_finished_width_m':portal_clear,'door_bounding_box_column_intersection_m2':door_bounds.intersection(unary_union(columns)).area,
          'actual_throat':portal},
          'Actual portal throat >= 1.20 m; door sweep clear of represented columns',portal['finished_unobstructed_width_m']>=1.20 and door_bounds.intersection(unary_union(columns)).area<1e-10,
          'Both door sweep and separate wall portal are checked. Column overlap cannot be erased by drawing an opening over it.')
    lift_soffit=roof['lift_cap_structural_top_z_m']-cap_t
    stair_soffit=roof['stair_cap_structural_top_z_m']-cap_t
    headroom=proposal_headroom(rows,geom,proposal,levels,objects)
    check('H03-C06','Accessibility 303.2',{'sample_count':headroom['sample_count'],'minimum_m':headroom['minimum']['headroom_m']},
          'Sampled tread clearances >= 1.90 m',headroom['below_1_90_m']==0,
          'Conservative proposed soffits and source beams only; new IFC, all-point finished routes and handrail supports still require verification')
    check('H03-C07','TMEC P10 planning table; project stair roof reservation',{'lift_overhead_m':lift_soffit-highest,'stair_roof_clear_m':stair_soffit-levels['RF']-s['finish_vertical_build_up_m']},
          'Lift >= 4.30 m overhead; stair roof clear >= project 2.40 m',lift_soffit-highest>=4.30 and stair_soffit-levels['RF']-s['finish_vertical_build_up_m']>=2.40,
          'Vendor feature/dimensional check, not structural capacity or manufacturer confirmation')
    rail=scheme['stair']
    clear=width-rail['wall_finish_m']-rail['handrail_wall_gap_m']-rail['handrail_diameter_m']
    check('H03-C08','Accessibility 207, 305; project 1.20 m clear flight target',{'nominal_clear_flight_m':clear,'margin_m':clear-rail['clear_flight_target_m'],
          'project_dimensional_allowance_m':s['dimensional_allowance_m']},
          'Retain 20 mm project allowance beyond the 1.20 m finished target',clear>=rail['clear_flight_target_m']+s['dimensional_allowance_m'],
          'The 20 mm allowance is a project choice, not a legal tolerance. Guard/bracket strength and finished construction remain unchecked.')
    roof_leaf=np.diff(roof['roof_door_rough_x_m'])[0]-2*roof['roof_door_frame_each_side_m']
    roof_gap=circle_gap(roof['roof_door_hinge_m'],roof_leaf,[centre,rows[-1]['b_end_y_m']],radius)
    check('H03-C09','Design/construction Articles 33(4), 76, 97',{'roof_door_disc_separation_m':roof_gap,
          'roof_door_nominal_clear_m':roof_leaf-roof['roof_door_leaf_thickness_m']},
          'RF south door clears the turn with 20 mm nominal margin and >= 0.90 m clear opening',roof_gap>=.02 and roof_leaf-roof['roof_door_leaf_thickness_m']>=.90,
          'Narrow wall-edge jamb, rated anchorage and roof drainage remain for structural/detail review; not a certified assembly')
    return {'revision':proposal['revision'],'status':'ARCHITECTURAL_PROPOSAL_FOR_STRUCTURAL_REVIEW',
            'rows':rows,'checks':checks,'headroom':headroom,
            'alternatives':{'unchanged_core_minimum_depth_m':minimum_depth,'unchanged_core_available_m':old_depth,
                            'minimum_depth_shortfall_m':minimum_depth-old_depth,
                            'basis':'Uniform 133.333 mm rises, minimum compliant tread, one mid-turn setback and two 1.30 m landings; arrangement-specific lower bound',
                            'reduced_first_storey_m':3.9,'reduced_first_storey_uniform_riser_m':.15},
            'existing_central_door_example':{'hinge_m':baseline_hinge,'leaf_m':1.1,'turn_radius_m':radius,'overlap_m2':baseline_overlap,
                                            'scope':'Disclosed nominal swing example in the existing opening, not a proof that every alternative hinge/door is impossible'},
            'structural_interfaces':interfaces,
            'quantity_screen':{'stair_enclosure_added_plan_m2':geom['outer'].area-old_outer.area,
                               'vestibule_outside_core_m2':vestibule.difference(geom['outer']).area,
                               'west_room_reservation_loss_m2':planning_loss,
                               'proposed_stair_horizontal_finish_m2':stair_area,
                               'proposed_risers':sum(sum(p) for p in s['risers_by_storey']),
                               'scope':'Geometric reservations/finish area only; not a priced bill or RC quantity certification'},
            'lift_and_roof':{'pit_finished_floor_z_m':pit_finished,'pit_rc_top_z_m':pit_finished-roof['pit_floor_build_up_m'],
                             'pit_rc_bottom_z_m':pit_finished-roof['pit_floor_build_up_m']-roof['pit_base_trial_thickness_m'],
                             'lift_cap_soffit_z_m':lift_soffit,'stair_cap_soffit_z_m':stair_soffit,
                             'counterweight_assumed_kg':counter,'permanent_equipment_assumed_kg':permanent,
                             'synthetic_load_envelopes':equipment,'roof_equipment_dead_kN':load_basis['roof']['synthetic_equipment_dead_kN'],
                             'load_application':'NOT_APPLIED_TO_H02'},
            'architectural_acceptance':False,'structural_geometry_adopted':False,'solver_executed':False,
            'holds':['Direct wall-column joint idealization, overlap ownership and structural adoption remain to be resolved',
                     'Ground discharge swing and all-point protected egress',
                     'Rated vestibule assemblies, handrail/guard details and finished tolerances',
                     'IFC/converter/GUID/connection review and load adoption',
                     'Equipment lateral/anchor loads, roof tank/MEP requirements and pit/foundation design']}


def draw(out,proposal,objects,levels,report,digest):
    geom=core_geometry(proposal,objects);x0,a1,b0,x1=geom['x'];rows=report['rows'];v=proposal['vestibule']
    leaf=np.diff(v['door_rough_y_m'])[0]-2*v['door_frame_each_side_m']
    outputs=[]
    for sheet_no,storeys in enumerate((('1F','2F'),('3F','RF')),3):
        sheet=Sheet(f'AH-00{sheet_no}','Proposed stair / protected side entry',digest,'H03-A')
        sheet.text(14,33,'PROPOSAL ONLY: structural IFC and H02 analysis still describe the previous geometry.',2.8,'#aa3a20')
        for panel,lv in enumerate(storeys):
            ox=17+panel*204;tr=lambda x,y,ox=ox:(ox+(x-4.0)*20,249-(y-3.0)*20)
            sheet.text(ox,43,f'{lv} | 1:50 | source level +{levels[lv]:.2f}',3.3)
            sheet.shape(geom['wall'],tr,'#abc3cc','#264d5e')
            # Retained lift and columns establish the architectural/structural interface.
            for o in objects.values():
                if o['kind'] in ('IFCCOLUMN','IFCWALL') and abs(o['min'][2])<1e-7:
                    if o['kind']=='IFCCOLUMN' and 4<o['min'][0]<12.4:
                        sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'#455965','#17313d',guid=o['guid'])
                    elif o['name'].startswith('SW-LIFT-'):
                        sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'#bdc9cf','#17313d',guid=o['guid'])
            # Preserve the existing lift door void; a gross wall projection is not a closed wall.
            if lv!='RF':
                lift_door=objects['OPEN-LIFT-DOOR-1F']
                sheet.shape(box(*lift_door['min'][:2],*lift_door['max'][:2]),tr,'white','#008575',guid=lift_door['guid'])
            sheet.shape(geom['outer'],tr,'none','#4276b7','1,1')
            vb=box(*v['outer_bounds_m']);vt=v['enclosure_thickness_m']
            vi=box(vb.bounds[0]+vt,vb.bounds[1]+vt,vb.bounds[2],vb.bounds[3]-vt)
            if lv!='RF':
                sheet.shape(vb.difference(vi),tr,'#d8c9e6','#665075')
                sheet.shape(box(objects['SW-STAIR-W-1F']['min'][0],v['side_portal_y_m'][0],x0,v['side_portal_y_m'][1]),tr,'white','#008575')
                sheet.shape(box(vb.bounds[0],v['door_rough_y_m'][0],vb.bounds[0]+vt,v['door_rough_y_m'][1]),tr,'white','#008575')
            if lv not in ('1F','RF'):
                sheet.shape(sector(v['door_hinge_m'],leaf,0,90),tr,'#d7efe2','#008575')
                hx,hy=v['door_hinge_m'];sheet.line(*tr(hx,hy),*tr(hx+leaf,hy),'#008575',.65)
            elif lv=='1F':
                sheet.text(*tr(4.1,4.0),'OUTWARD DISCHARGE / HOLD',2.5,'#aa3a20')
            else:
                roof=proposal['lift_and_roof'];rx0,rx1=roof['roof_door_rough_x_m']
                sheet.shape(box(rx0,geom['outer'].bounds[1],rx1,geom['inner'].bounds[1]),tr,'white','#008575')
                roof_leaf=rx1-rx0-2*roof['roof_door_frame_each_side_m']
                sheet.shape(sector(roof['roof_door_hinge_m'],roof_leaf,0,90),tr,'#d7efe2','#008575')
            i=('1F','2F','3F','RF').index(lv)
            row=rows[min(i,2)]
            if i:
                incoming=rows[i-1];y=incoming['b_end_y_m']
                sheet.shape(sector([(x0+x1)/2,y],proposal['stair']['turning_envelope_radius_m'],180,360),tr,'#edf3df','#688341','1,1')
                sheet.text(*tr(6.6,y-.50),f'Arrive B: y={y:.2f}',2.4)
            for letter,lo,hi,start,end,n in (('A',x0,a1,row['a_start_y_m'],row['a_end_y_m'],row['a_risers']),
                                           ('B',b0,x1,row['b_start_y_m'],row['b_end_y_m'],row['b_risers'])):
                dash='1,1' if lv=='RF' else ''
                sheet.shape(box(lo,min(start,end),hi,max(start,end)),tr,'#f0f4f4','#3c6866',dash)
                for y in np.linspace(start,end,n):sheet.line(*tr(lo,y),*tr(hi,y),'#3c6866',.18,dash)
                sheet.text(*tr(lo+.08,(start+end)/2),f'{letter}: {n}R',2.8)
            sheet.shape(landing_polygon(row,geom),tr,'#e7ebe0','#688341')
            sheet.text(*tr(6.5,10.9),f'MID FFL +{row["mid_ffl_m"]:.3f}',2.5)
            sheet.text(*tr(6.5,10.55),'One tread setback: 0.29',2.4)
            sheet.text(*tr(9.7,8.6),'Core inside 2.80 x 7.30',2.35)
            sheet.text(*tr(9.7,8.2),'W / well / W = 1.30 / 0.20 / 1.30',2.2)
            sheet.text(*tr(9.7,7.8),'South +0.65; north +0.25 extension',2.2)
            sheet.text(*tr(9.6,5.6),'OVERRUN / NO STOP' if lv=='RF' else 'LIFT',2.5)
            if lv!='RF':
                sheet.text(*tr(4.15,6.55),'Side portal 1.30 rough / 1.28 finished',2.1)
                sheet.text(*tr(4.15,6.28),'Stair wall opening: y 4.60 to 5.90',2.1)
            else:
                sheet.text(*tr(4.15,6.55),'South roof door: 1.005 nominal clear',2.1)
                sheet.text(*tr(4.15,6.28),'No west vestibule at RF',2.1)
            for y in (4.2,11.7):
                sheet.line(*tr(4.0,y),*tr(12.0,y),'#4276b7',.15,'2,1')
            sheet.text(ox,259,'30 / 27 / 27 rises; R=133.333 mm; T=290 mm',2.6)
            sheet.text(ox,264,'Clear flight 1.208: 8 mm margin / detailing HOLD. Purple: vestibule.',2.35)
            if lv=='RF':sheet.text(ox,269,'Flights below RF shown; rooftop door/landing detail remains open.',2.35,'#aa3a20')
            else:sheet.text(ox,269,'Portal and L-shaped landing edges require structural IFC revision.',2.35,'#aa3a20')
        name=f'AH-00{sheet_no}-core.svg';sheet.write(out/name);outputs.append(name)
    sheet=Sheet('AH-005','Finished stair sections and lift / roof interface',digest,'H03-A')
    sheet.text(14,33,'Finished nosings / proposed envelopes. RC supports and new equipment loads are not analyzed.',2.8,'#aa3a20')
    for panel,letter in enumerate(('A','B')):
        ox=16+panel*135;tr=lambda y,z,ox=ox:(ox+(y-3.8)*16,253-z*14)
        sheet.text(ox,44,f'Flight {letter} longitudinal section | schematic scales H 1:62.5 / V 1:71.4',2.45)
        for row in rows:
            if letter=='A':start,base,n,d=row['a_start_y_m'],row['lower_ffl_m'],row['a_risers'],1
            else:start,base,n,d=row['b_start_y_m'],row['mid_ffl_m'],row['b_risers'],-1
            r,t=row['riser_m'],row['tread_m'];pts=[(start,base)]
            for k in range(n):
                y=start+d*k*t;pts.append((y,base+(k+1)*r))
                if k<n-1:pts.append((y+d*t,base+(k+1)*r))
            for a,b in zip(pts,pts[1:]):sheet.line(*tr(*a),*tr(*b),'#225c63',.45)
            # Step setback is deliberately visible; this is not a rectangular mid-landing.
            end=start+d*(n-1)*t
            waist=proposal['stair']['nominal_waist_normal_thickness_m']*math.sqrt(1+(r/t)**2)
            finish=proposal['stair']['finish_vertical_build_up_m']
            sheet.line(*tr(start,base-finish-waist),*tr(end,base-finish+(n-1)*r-waist),'#aa7956',.25,'1,1')
            mid_y=row['a_end_y_m'] if letter=='A' else row['b_start_y_m']
            sheet.line(*tr(mid_y,row['mid_ffl_m']),*tr(11.4,row['mid_ffl_m']),'#225c63',.5)
            # A floor approach is solid in the proposal; floor-hole edge follows its first nosing.
            floor_y=row['a_start_y_m'] if letter=='A' else row['b_end_y_m']
            floor_z=row['lower_ffl_m'] if letter=='A' else row['upper_ffl_m']
            sheet.line(*tr(4.1,floor_z),*tr(floor_y,floor_z),'#225c63',.5)
            sheet.text(*tr(min(start,end),base+.9),f'{n}R / {n-1}T',2.2)
            for z in (row['lower_ffl_m'],row['mid_ffl_m'],row['upper_ffl_m']):
                sheet.line(*tr(4.1,z),*tr(11.4,z),'#b8c2c9',.15,'1,1')
        for lv,z in levels.items():
            sheet.text(*tr(4.0,z+.12),f'{lv} SSL {z:.2f}',2.2)
        cap=proposal['lift_and_roof']['stair_cap_structural_top_z_m']
        sheet.rect(*tr(3.85,cap),7.8*16,.18*14,'#aebcc6','#17313d')
        sheet.text(*tr(4.1,12.6),'Roof clear 2.42 m',2.7)
    x=296;roof=report['lift_and_roof'];p=proposal['lift_and_roof']
    tr=lambda y,z:(x+(y-4.5)*27,253-z*14)
    sheet.text(x,44,'Lift section / vertical reservations',3)
    sheet.line(*tr(4.5,-1.8),*tr(4.5,12.25),'#17313d',.6)
    sheet.line(*tr(7.05,-1.8),*tr(7.05,12.25),'#17313d',.6)
    for lv,z in levels.items():
        sheet.line(*tr(4.3,z),*tr(7.25,z),'#80949c',.2,'1,1')
        sheet.text(*tr(7.1,z+.1),lv,2.5)
    sheet.rect(*tr(4.5,12.25),2.55*27,.18*14,'#aebcc6','#17313d')
    sheet.rect(*tr(4.5,roof['pit_rc_top_z_m']),2.55*27,.30*14,'#aebcc6','#17313d')
    sheet.text(*tr(4.6,12.6),'Cap SSL +12.25',2.7)
    sheet.text(*tr(4.6,11.6),'Soffit +12.07',2.7)
    sheet.text(*tr(4.6,9.5),'Overhead 4.42 m',2.7)
    sheet.text(*tr(4.6,1.1),'Pit clear depth 1.50 m',2.6)
    sheet.text(*tr(4.6,-.7),'Pit FFL -1.45',2.6)
    sheet.text(296,270,'Pit RC bottom -1.80; H02 trial fixity -1.20.',2.5,'#aa3a20')
    sheet.text(16,270,'Sampled proposed headroom passes; full finished IFC / door / guard / foundation review remains open.',2.6,'#aa3a20')
    sheet.text(16,265,'Brown dashed line: conservative soffit used for screening; support/anchorage is not detailed.',2.6)
    name='AH-005-sections.svg';sheet.write(out/name);outputs.append(name)
    sheet=Sheet('AH-006','Whole-floor architectural coordination proposal',digest,'H03-A')
    sheet.text(14,33,'2F reference layout; same room reservations on 1F/3F. Stair details vary by floor: AH-003 / AH-004.',2.8)
    tr=lambda x,y:(18+x*14.5,235-y*14.5)
    sheet.shape(box(0,0,18,12),tr,'#f7f9f9','#17313d')
    reservations=unary_union([geom['outer'],box(*v['outer_bounds_m']),box(*v['protected_approach_bounds_m'])])
    for room in proposal['_retained_spaces']:
        region=box(*room['bounds_m']).difference(reservations)
        sheet.shape(region,tr,'#e0eef1' if room['occupied'] else '#eee3f4','#718b94')
        pt=region.representative_point()
        sheet.text(*tr(pt.x-.4,pt.y),room['id'],3)
    sheet.shape(box(*v['protected_approach_bounds_m']),tr,'#e3ecd8','#688341','1,1')
    for o in objects.values():
        if o['kind']=='IFCCOLUMN' and abs(o['min'][2])<1e-8:
            sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'#455965','#17313d',guid=o['guid'])
        if o['name'].startswith('SW-LIFT-') and abs(o['min'][2])<1e-8:
            sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'#bdc9cf','#17313d',guid=o['guid'])
        if o['kind']=='IFCBEAM' and abs(o['max'][2]-levels['3F'])<1e-8:
            sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'none','#4276b7','1,1',guid=o['guid'])
    sheet.shape(geom['wall'],tr,'#abc3cc','#264d5e')
    vb=box(*v['outer_bounds_m']);vt=v['enclosure_thickness_m']
    sheet.shape(vb.difference(box(vb.bounds[0]+vt,vb.bounds[1]+vt,vb.bounds[2],vb.bounds[3]-vt)),tr,'#d8c9e6','#665075')
    for rect in [box(objects['SW-STAIR-W-1F']['min'][0],v['side_portal_y_m'][0],x0,v['side_portal_y_m'][1]),
                 box(vb.bounds[0],v['door_rough_y_m'][0],vb.bounds[0]+vt,v['door_rough_y_m'][1]),
                 box(*objects['OPEN-LIFT-DOOR-1F']['min'][:2],*objects['OPEN-LIFT-DOOR-1F']['max'][:2])]:
        sheet.shape(rect,tr,'white','#008575')
    sheet.shape(sector(v['door_hinge_m'],leaf,0,90),tr,'#d7efe2','#008575')
    for a,b in zip(v['protected_route_centerline'],v['protected_route_centerline'][1:]):
        sheet.line(*tr(*a),*tr(*b),'#008575',.5,'1,1')
    for name,a,b in [('A',rows[1]['a_start_y_m'],rows[1]['a_end_y_m']),('B',rows[1]['b_end_y_m'],rows[1]['b_start_y_m'])]:
        lo,hi=(x0,a1) if name=='A' else (b0,x1)
        sheet.shape(box(lo,a,hi,b),tr,'#f0f4f4','#3c6866');sheet.text(*tr(lo+.1,(a+b)/2),name,3)
    sheet.shape(landing_polygon(rows[1],geom),tr,'#e7ebe0','#688341')
    sheet.text(*tr(9.7,5.7),'LIFT',2.8)
    notes=[
        'ARCHITECTURAL REVISION',
        'Floor elevations: 0 / 4.0 / 7.6 / 11.2 m.',
        'Main columns and beam lines retained.',
        'Stair enclosure: +2.97 m2 per level.',
        'Side vestibule outside core: 3.06 m2.',
        'West room W1 reservation: -4.72 m2.',
        'New protected approach in green.',
        '',
        'STRUCTURAL RESPONSE REQUIRED',
        'New west wall portal beside B2.',
        'North enclosure meets rear beam zone.',
        'Review joints and wall/beam overlap.',
        'Resolve all-point egress and ground exit.',
        'Detail handrail/guard width tolerance.',
        'WC and service routing still on hold.',
        '',
        'W1 west office; E1 east office;',
        'M1 meeting; B1 staff; WC1/WC2 services.',
        'Reservations only; partitions/furniture',
        'and full accessibility are not accepted.'
    ]
    for i,line in enumerate(notes):sheet.text(291,59+i*6.8,line,2.7)
    sheet.text(18,247,'Blue dashed: retained beams above 2F. Green dashed: proposed corridor centreline, not an egress approval.',2.6)
    sheet.text(18,255,'H02 AH-002 is a historical room-layout reference; use this sheet with H03-A core details for the proposed revision.',2.6,'#aa3a20')
    sheet.text(18,263,'Roof and pit sections: AH-005. Actual structural IFC / loads remain H02 until the coordinated adoption review.',2.6,'#aa3a20')
    name='AH-006-floor.svg';sheet.write(out/name);outputs.append(name)
    html='<!doctype html><html lang="en"><meta charset="utf-8"><title>H03-A architectural core proposal</title><style>@page{size:A3 landscape;margin:0}body{margin:0}img{display:block;width:420mm;height:297mm;break-after:page}</style>'+''.join(f'<img src="{n}" alt="{n}">' for n in outputs)+'</html>'
    (out/'core-proposal.html').write_text(html)
    return outputs


def core_review_project(directory: Path):
    from .cli import load_project, architectural_scheme, received_scheme
    directory,project,source,analysis,root=load_project(directory)
    received_source=received_scheme(directory,project)
    proposal_path=(directory/project['architectural_handoff']['core_proposal']).resolve()
    load_path=directory/'structural/design/core-interface-loads.yaml'
    if not proposal_path.is_relative_to(directory):raise ValueError('Proposal must remain in the project')
    proposal=yaml.safe_load(proposal_path.read_text());basis=yaml.safe_load(load_path.read_text())
    scheme_path=architectural_scheme(directory,project);scheme=yaml.safe_load(scheme_path.read_text())
    if proposal.get('revision') not in ('H03-A','H03-B') or basis.get('revision')!=proposal['revision']:
        raise ValueError('Review the core proposal schema before changing revisions')
    out,manifest=make_run(root,project['id'],'core-proposal')
    manifest['command']=['python','-m','structural_ai','core-review','--project',directory.relative_to(root).as_posix()]
    try:
        _,received,_,_,_,levels=read_geometry(received_source)
        geometry_source=source
        if proposal['revision']=='H03-B':
            geometry_source=(directory/project['architectural_handoff']['core_candidate_ifc']).resolve()
            if not geometry_source.is_relative_to(directory):raise ValueError('Candidate must remain inside the project')
            if file_hash(geometry_source)!=project['architectural_handoff']['core_candidate_sha256']:
                raise ValueError('Candidate IFC changed; repeat source and converter review')
            from .core_revision import revise_core
            receipt=revise_core(received_source,proposal,out/'regenerated-candidate.ifc',scheme)
            write_json(out/'candidate-source-review.json',receipt)
            if file_hash(out/'regenerated-candidate.ifc')!=file_hash(geometry_source):
                raise ValueError('Proposal/scheme and candidate IFC differ; regenerate and review before drawing')
        _,objects,_,_,_,levels=read_geometry(geometry_source)
        report=evaluate(proposal,basis,scheme,objects,levels,yaml.safe_load(analysis.read_text())['materials']['g_m_s2'],received)
        report['source_sha256']=file_hash(source)
        report['candidate_geometry_sha256']=file_hash(geometry_source)
        adopted=yaml.safe_load(analysis.read_text())['revision']=='H03-C'
        if adopted:
            if file_hash(source)!=file_hash(geometry_source):
                raise ValueError('Adopted structural source and architectural review geometry differ')
            adoption=json.loads((directory/'structural/outputs/deliverables/model-adoption.json').read_text())
            for path in (source,analysis):
                if adoption['after_sha256'].get(path.relative_to(root).as_posix())!=file_hash(path):
                    raise ValueError('Drawing inputs differ from the controlled structural adoption receipt')
            if adoption['equipment_authority_sha256']!=file_hash(load_path):
                raise ValueError('Drawing equipment basis differs from the controlled adoption receipt')
            report['structural_verification_run_id']=adoption['verification_run_id']
            report['structural_geometry_adopted']=True
            report['architectural_geometry_revision']=proposal['revision']
            report['revision']='H03-C'
            report['status']='DIAGNOSTIC_GEOMETRY_ADOPTED_ARCHITECTURAL_ACCEPTANCE_OPEN'
            report['structural_adoption_scope']='H03-C gross elastic diagnostic basis; full code/RC/foundation design remains open'
            report['lift_and_roof']['load_application']='APPLIED_TO_H03_C_DIAGNOSTICS_NOT_VENDOR_SUPPORT_DESIGN'
            report['holds']=[value for value in report['holds']
                if not value.startswith(('Direct wall-column','IFC/converter/GUID'))]
            report['holds'].append('Current code actions, RC joint/member reinforcement and foundations remain incomplete')
        report['input_sha256']={p.relative_to(root).as_posix():file_hash(p) for p in (source,received_source,analysis,scheme_path,proposal_path,load_path,geometry_source)}
        report['independent_ifc_objects_checked']=len(objects)
        write_json(out/'core-review.json',report)
        if proposal['revision']=='H03-B':
            from .core_candidate import draw_candidate
            draw_candidate(out,proposal,objects,levels,report,file_hash(geometry_source))
        else:draw(out,{**proposal,'_retained_spaces':scheme['spaces']},objects,levels,report,file_hash(source))
        finish_run(out,manifest,('COMPLETED_ARCHITECTURAL_REVIEW_WITH_DIAGNOSTIC_GEOMETRY_ADOPTED' if adopted else
                               'COMPLETED_ARCHITECTURAL_PROPOSAL_WITH_STRUCTURAL_ADOPTION_HOLD'),exit_code=0,
                   architectural_acceptance=False,structural_geometry_adopted=adopted)
    except Exception:
        (out/'failure.txt').write_text(traceback.format_exc())
        finish_run(out,manifest,'FAILED',exit_code=1)
        raise
    return out
