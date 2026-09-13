"""Architectural core review drawings with explicit diagnostic adoption status."""
from shapely.geometry import box, LineString
from .coordination import Sheet
from .core_review import core_geometry, landing_polygon, sector


def draw_candidate(out, proposal, objects, levels, report, digest):
    adopted=report.get('structural_geometry_adopted',False)
    revision='CASE STUDY' if adopted else 'PROPOSAL'
    numbers=('AR-001','AR-002') if adopted else ('AH-007','AH-008')
    names=['architectural-plan.svg','entrance-detail.svg'] if adopted else [numbers[0]+'-candidate.svg',numbers[1]+'-portal.svg']
    source_label='Architectural model / verified diagnostic basis' if adopted else 'core-candidate.ifc / unadopted'
    geom=core_geometry(proposal,objects);v=proposal['vestibule'];s=proposal['stair']
    x0,a1,b0,x1=geom['x'];row=report['rows'][1]
    check=next(c for c in report['checks'] if c['id']=='H03-C05')['value']['actual_throat']
    sheet=Sheet(numbers[0],'Core and retained frame: structural coordination review',digest,revision,source_label)
    sheet.text(14,33,('Architectural geometry checked for diagnostics. Full architecture, code actions, reinforcement and foundations remain open.' if adopted else
                      'H03-B CANDIDATE ONLY. Direct wall-column joints require review. H02 remains the adopted structural model.'),2.9,'#a52d25')
    tr=lambda x,y:(18+x*14.5,235-y*14.5)
    sheet.shape(box(0,0,18,12),tr,'#f8faf9','#183848')
    for o in objects.values():
        if o['kind']=='IFCBEAM' and abs(o['max'][2]-levels['3F'])<1e-8:
            sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'none','#628ca4','1,1',guid=o['guid'])
        if o['kind']=='IFCWALL' and abs(o['min'][2])<1e-8:
            sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'#cfdeea' if o['name'].startswith('SW-') else '#e6daed','#527184',guid=o['guid'])
    for o in objects.values():
        if o['kind']=='IFCOPENINGELEMENT' and 'DOOR' in o['name'] and abs(o['min'][2])<1e-8:
            sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'white','#34795d',guid=o['guid'])
    for letter,lo,hi,start,end,n in [('A',x0,a1,row['a_start_y_m'],row['a_end_y_m'],row['a_risers']),
                                    ('B',b0,x1,row['b_end_y_m'],row['b_start_y_m'],row['b_risers'])]:
        sheet.shape(box(lo,start,hi,end),tr,'#e4ebe6','#47726b')
        for k in range(n):sheet.line(*tr(lo,start+k*s['tread_m']),*tr(hi,start+k*s['tread_m']),'#47726b',.16)
        sheet.text(*tr(lo+.2,(start+end)/2),letter,3)
    sheet.shape(landing_polygon(row,geom),tr,'#e7ecdc','#6c7d48')
    # Columns are drawn last so that a white opening cannot erase a real obstruction.
    for o in objects.values():
        if o['kind']=='IFCCOLUMN' and abs(o['min'][2])<1e-8:
            sheet.shape(box(*o['min'][:2],*o['max'][:2]),tr,'#455a66','#1b3643',guid=o['guid'])
    for c in check['column_conflicts']:
        sheet.shape(box(*c['throat_intersection_bounds_m']),tr,'#f17162','#ad211b')
    sheet.shape(box(*v['protected_approach_bounds_m']),tr,'none','#538751','1,1')
    notes=['2F REFERENCE PLAN / 1:69',
           '36 source columns / 51 source beams retained.',
           'Orthogonal beams and 7.50 m rear bay retained.',
           'Shared stair / lift wall retained.',
           '', 'ARCHITECTURAL GEOMETRY',
           'Flight / well / flight: 1.33 / 0.22 / 1.33 m.',
           'Finished flight: 1.238 m; 38 mm nominal margin.',
           'Uniform rises: 133.333 mm; treads: 290 mm.',
           'North edge +11.68; south edge +3.50 m.',
           'Lightweight vestibules: load only, no RC stiffness.',
           'Caps +13.85 / +12.25 m; pit RC bottom -1.80 m.',
           '', 'STRUCTURAL ADOPTION HOLD',
           'B2 clears the portal by 0.10 m in plan.',
           'Actual finished throat: 1.28 m > target 1.20 m.',
           'See AH-008. Review monolithic wall-column joints.',
           'Floor connectivity is not a full joint design.',
           '', 'No RC reinforcement or foundation approval.',
           'Not a coordinated construction package.']
    if adopted:
        notes[13]='DIAGNOSTIC GEOMETRY ADOPTED'
        notes[16]='See AR-002 and SR-001/002 interface review.'
        notes[17]='Elastic joint action checked; RC design remains open.'
    for i,text in enumerate(notes):sheet.text(291,52+i*7,text,2.5,'#a52d25' if 13<=i<=17 else '#183848')
    sheet.text(18,250,'Blue dashed: retained beams above. Columns drawn last: opening graphics cannot erase physical columns.',2.65)
    sheet.text(18,259,('This geometry matches the structural input. Architectural and construction acceptance are not complete.' if adopted else
                       'This sheet supersedes H03-A as the current issue review; the candidate is held, not adopted.'),2.65,'#a52d25')
    sheet.write(out/names[0])

    sheet=Sheet(numbers[1],'B2 wall joint and entry detailing screens',digest,revision,source_label)
    sheet.text(14,33,('The portal clears B2. Wall-column elastic force transfer is modelled; joint reinforcement and full egress remain open.' if adopted else
                      'The portal clears B2. The wall intersects the column below the portal; direct joint action remains undesigned.'),2.9,'#a52d25')
    tr=lambda x,y:(20+(x-3.0)*43,216-(y-3.0)*43)
    sheet.text(20,48,'1F PLAN DETAIL / 1:23.3',3.1)
    vb=box(*v['outer_bounds_m']);t=v['enclosure_thickness_m']
    sheet.shape(vb.difference(box(vb.bounds[0]+t,vb.bounds[1]+t,vb.bounds[2],vb.bounds[3]-t)),tr,'#e6daed','#775a88')
    w=objects['SW-STAIR-W-1F'];sheet.shape(box(w['min'][0],3.5,w['max'][0],6.4),tr,'#cfdeea','#527184')
    sheet.shape(box(w['min'][0]-.02,*[v['side_portal_y_m'][0]],w['max'][0]+.02,v['side_portal_y_m'][1]),tr,'white','#34795d')
    sheet.shape(box(vb.bounds[0],v['door_rough_y_m'][0],vb.bounds[0]+t,v['door_rough_y_m'][1]),tr,'white','#34795d')
    leaf=v['door_rough_y_m'][1]-v['door_rough_y_m'][0]-2*v['door_frame_each_side_m']
    hinge=v['ground_door_hinge_m'];sheet.shape(sector(hinge,leaf,180,270),tr,'#e2eddf','#538751')
    sheet.line(*tr(*hinge),*tr(hinge[0]-leaf,hinge[1]),'#34795d',.7)
    sheet.shape(box(*v['ground_south_route_bounds_m']),tr,'none','#538751','1,1')
    sheet.shape(box(x0,5.9,a1,6.4),tr,'#e4ebe6','#47726b')
    o=objects['C-B2-1F'];column=box(*o['min'][:2],*o['max'][:2])
    sheet.shape(column,tr,'#455a66','#1b3643',guid=o['guid'])
    intersection=column.intersection(box(*w['min'][:2],*w['max'][:2]))
    sheet.shape(intersection,tr,'#f1aa62','#a9641b')
    sheet.text(*tr(5.80,4.10),'B2',3.5,'white')
    sheet.text(*tr(5.30,5.22),'1.28 m clear',2.7,'#34795d')
    sheet.text(*tr(3.16,3.45),'South route reservation',2.5)
    notes=['SOURCE-BASED THROAT CHECK',
           'Portal y = 4.60 to 5.90 m.',
           'B2 column reaches y = 4.50 m.',
           'Unobstructed raw interval = 4.60 to 5.90 m.',
           'After two 10 mm finishes: 1.28 m.',
           'Project passage target: 1.20 m. Nominal pass.',
           '', 'OTHER NOMINAL DETAIL SCREENS',
           'Ground top hinge opens west; full leaf is north',
           'of the reserved south route. Full egress is open.',
           'RF jamb: 0.40 m geometric wall length.',
           'RF door-to-turn disc gap: 43 mm.',
           'Guard: 1.10 m; vertical infill openings <=90 mm.',
           'Central guard / rails fit in the 0.22 m well.',
           'Rated assemblies and all anchorage are unverified.',
           '', 'NEXT STRUCTURAL IMPLEMENTATION',
           'Resolve direct wall-column joint idealization,',
           'shared concrete quantity and eccentric forces.',
           'Current connection is through floor-level beams/slabs.',
           'Verify joint constraints before source adoption.',
           'Update analysis, quantities and drawings together.']
    if adopted:
        notes[16:] = ['REMAINING STRUCTURAL DESIGN',
                      'Current code actions, combinations and system checks;',
                      'beam/column/wall/slab/stair and joint reinforcement;',
                      'anchorage, foundations and construction details;',
                      'priced quantities and construction feasibility.',
                      'Elastic joint verification does not close these gates.']
    for i,text in enumerate(notes):sheet.text(245,51+i*8.0,text,2.65,'#a52d25' if i in (5,16) else '#183848')
    sheet.text(20,245,'The 1.20 m target is a recorded project screen; this is not a complete statutory egress review.',2.6)
    sheet.text(20,255,'Ground door and guard lines are geometric reservations; certified products and reinforcement are not designed.',2.6)
    sheet.text(20,265,'Main-frame solid geometry and GUIDs remain unchanged. Solver equilibrium does not clear this architectural hold.',2.6,'#a52d25')
    sheet.write(out/names[1])
    (out/'core-proposal.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>'+revision+' architectural review</title><style>@page{size:A3 landscape;margin:0}body{margin:0}img{display:block;width:420mm;height:297mm;break-after:page}</style>'+''.join(f'<img src="{n}" alt="{n}">' for n in names)+'</html>')
    return names
