"""H02 simulated architectural proposal and structural transfer review sheets.

Room reservations and selected route screens are not a complete architectural
model, all-point egress assessment, accessibility audit or construction drawings.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import traceback
import textwrap

import numpy as np
from shapely.geometry import box, LineString, Point
from shapely.ops import unary_union
import yaml

from .cli import load_project, architectural_scheme
from .coordination import read_geometry, Sheet, projected_beams
from .provenance import RUNS_RELATIVE, file_hash, verify_build_inputs, make_run, finish_run, write_json


def proposal_checks(scheme, objects, levels):
    obstacles = unary_union([box(*o['min'][:2], *o['max'][:2]) for o in objects.values()
                            if o['kind'] in ('IFCCOLUMN', 'IFCWALL') and abs(o['min'][2]) < 1e-7])
    spaces = []
    for s in scheme['spaces']:
        polygon = box(*s['bounds_m']).difference(obstacles)
        spaces.append({**s, 'planning_net_area_m2': polygon.area,
                       'scope': 'Reservation minus source wall/column footprints; no partition/furniture/statutory area certification'})
    routes = []
    for key in ('main_route', 'east_route'):
        line = LineString(scheme['circulation'][key])
        # The final approach ends at the wall opening. Truncate that endpoint
        # before the body-width screen; the door/turn has its own explicit HOLD.
        coords = list(line.coords)
        coords[-1] = (coords[-1][0], coords[-1][1]-.65)
        body = LineString(coords).buffer(scheme['circulation']['corridor_target_clear_m']/2,
                                       cap_style=2, join_style=2)
        conflict = body.intersection(obstacles).area
        routes.append({'id': key, 'length_m': line.length,
                       'structural_obstacle_intersection_m2': conflict,
                       'status': 'CLEAR_OF_REPRESENTED_STRUCTURE_ONLY' if conflict < 1e-8 else 'CONFLICT',
                       'limit_m': 50., 'clause': 'Design/construction Article 93 ordinary-use route',
                       'code_compliance': 'NOT_CHECKED_ALL_POINTS_PARTITIONS_DOORS_AND_FURNITURE'})
    lift = scheme['lift']
    # Source-specific floor void. A fuzzy LIFT/2F name match also finds the door.
    shaft = objects['OPEN-LIFT-2F']
    available = np.array(shaft['max'][:2])-shaft['min'][:2]-2*lift['shaft_finish_per_face_m']
    margin = available-lift['minimum_finished_shaft_m']
    finished_low = levels['1F']+scheme['finishes']['occupied_floor_build_up_m']
    finished_high = levels['3F']+scheme['finishes']['occupied_floor_build_up_m']
    lift_screen = {'source_guid': shaft['guid'], 'finished_shaft_available_m': available.tolist(),
                   'nominal_dimension_margin_m': margin.tolist(),
                   'pit_bottom_reservation_z_m': finished_low-lift['pit_depth_below_lowest_finished_floor_m'],
                   'minimum_overhead_soffit_z_m': finished_high+lift['overhead_above_highest_finished_floor_m'],
                   'status': 'DIMENSIONAL_CANDIDATE_ONLY',
                   'engineering_load_status': 'NOT_INCLUDED_EQUIPMENT_AND_ENCLOSURE_REACTIONS_UNRESOLVED'}
    stair = scheme['stair']
    raw_width = objects['STF-1F-A']['max'][0]-objects['STF-1F-A']['min'][0]
    outer = stair['wall_finish_m']+stair['handrail_wall_gap_m']+stair['handrail_diameter_m']
    well = objects['STF-1F-B']['min'][0]-objects['STF-1F-A']['max'][0]
    required = stair['central_guard_thickness_m']+2*(stair['handrail_wall_gap_m']+stair['handrail_diameter_m'])
    return {'spaces': spaces, 'routes': routes, 'lift': lift_screen,
            'stairs': {'nominal_clear_flight_m': raw_width-outer, 'central_well_remaining_m': well-required,
                       'status': 'RESERVATION_ONLY_TURNS_DOORS_FINISH_TRANSITIONS_AND_UNIFORMITY_ON_HOLD'},
            'occupied_reservation_area_per_level_m2': sum(s['planning_net_area_m2'] for s in spaces if s['occupied']),
            'overall_status': 'PROPOSAL_WITH_HOLDS', 'architectural_acceptance': False,
            'final_design_complete': False, 'engineering_approval': False}


def draw_proposal(out, scheme, objects, levels, report, transfer, digest):
    sheet = Sheet('AH-002', 'Office layout and coordination reservations', digest, 'H02')
    scale = 12.
    tr = lambda x, y: (20+x*scale, 191-y*scale)
    sheet.text(20, 36, 'Typical 1F / 2F / 3F planning reservations | north up | 1:83.3', 3.2)
    sheet.shape(box(0, 0, 18, 12), tr, '#f5f8f8', '#17313d')
    for s in report['spaces']:
        polygon = box(*s['bounds_m'])
        sheet.shape(polygon, tr, '#e0eef1' if s['occupied'] else '#eee3f4', '#6c8792', '1,1')
        x, y = tr(polygon.centroid.x, polygon.centroid.y)
        width=(s['bounds_m'][2]-s['bounds_m'][0])*scale
        lines=textwrap.wrap(s['name'],width=max(10,int(width/1.45)-2))
        left=tr(s['bounds_m'][0],0)[0]+2
        for i,line in enumerate(lines): sheet.text(left,y-3.5*len(lines)/2+i*3.5,line,2.6)
        sheet.text(left,y+3.5*len(lines)/2+1,f"{s['id']}  {s['planning_net_area_m2']:.2f} m2",2.4)
        dx, dy = tr(*s['door_xy_m'])
        half=s['door_clear_m']*scale/2
        if any(abs(s['door_xy_m'][0]-s['bounds_m'][i])<1e-7 for i in (0,2)):
            sheet.line(dx,dy-half,dx,dy+half,'#008575',1.)
        else:
            sheet.line(dx-half,dy,dx+half,dy,'#008575',1.)
    hall = scheme['circulation']['protected_hall_bounds_m']
    sheet.shape(box(*hall), tr, '#e2f3df', '#008575', '1,1')
    sheet.text(*tr(6.9, 1.2), 'Protected hall', 2.8)
    for o in objects.values():
        if o['kind'] in ('IFCCOLUMN', 'IFCWALL') and abs(o['min'][2]) < 1e-7:
            sheet.shape(box(*o['min'][:2], *o['max'][:2]), tr, '#aebbc0', '#17313d', guid=o['guid'])
        if o['kind']=='IFCOPENINGELEMENT' and 'DOOR' in o['name'] and abs(o['min'][2]) < .2:
            sheet.shape(box(*o['min'][:2], *o['max'][:2]), tr, 'white', '#ad3724')
    for o in projected_beams(objects, levels, '1F'):
        sheet.shape(box(*o['min'][:2], *o['max'][:2]), tr, 'none', '#9cabb1', '1,1')
    for name in ('STF-1F-A', 'STF-1F-B', 'STL-1F-MID'):
        o = objects[name]
        sheet.shape(box(*o['min'][:2], *o['max'][:2]), tr, '#e0e5e7', '#536d77')
    upper_landing=objects['STL-2F-MID']
    sheet.line(*tr(upper_landing['min'][0],upper_landing['min'][1]),
               *tr(upper_landing['max'][0],upper_landing['min'][1]),'#ad3724',.4,'1,1')
    sheet.text(*tr(6.6, 8.5), 'Stair / HOLD', 2.8, '#ad3724')
    sheet.text(*tr(9.6, 5.9), 'Lift candidate', 2.6)
    for key in ('main_route', 'east_route'):
        coords = scheme['circulation'][key]
        for a, b in zip(coords, coords[1:]):
            sheet.line(*tr(*a), *tr(*b), '#008575', .7)
    circle = scheme['circulation']['lift_turn_circle']
    sheet.shape(Point(*circle['center_m']).buffer(circle['diameter_m']/2), tr, 'none', '#008575', '.5,.5')
    for key in ('main_exit', 'secondary_exit'):
        x, y = tr(*scheme['site'][key]['xy_m'])
        sheet.text(x-7, y+5, '1F EXIT', 2.7, '#008575')
    sheet.text(252, 40, 'SIMULATED ARCHITECTURAL BRIEF', 3.5)
    notes = [
        'G-2 private office; 20 persons/storey assumed.',
        'Room uses repeat on 1F-3F; furniture not fixed.',
        f"Occupied reservations: {report['occupied_reservation_area_per_level_m2']:.2f} m2/storey.",
        'Areas exclude represented columns/walls only.',
        'Dashed room bounds are planning reservations.',
        'Grey dashed lines: retained overhead main beams.',
        'Stair projection shows 1F; red dash: upper landing.',
        'Green lines: selected route corridors, target 1.20 m.',
        'Not an all-point egress or permit-area assessment.',
        '', 'HOLD H02-01  stair fire-door swing / landing turn',
        'HOLD H02-02  153.846 / 150 mm riser uniformity',
        'HOLD H02-03  WC fixtures, service route and MEP',
        'HOLD H02-04  lift entrance, reactions, pit / roof',
        '', 'Safety stair: proposed fire/smoke enclosure.',
        'Final fire-rated partitions and assemblies required.',
        'No new openings or beam cuts adopted.',
        'Exterior lighting/windows/facade not yet designed.',
        'Roof maintenance access only; no lift roof stop.',
        'Source geometry unchanged; IFC is structural input.',
    ]
    for i, line in enumerate(notes): sheet.text(252, 48+i*5.2, line, 2.65)
    sheet.text(20, 207, '1F discharge site reservation (synthetic; not a surveyed or zoning-compliant parcel)', 3.2)
    site_tr = lambda x, y: (24+(x+2)*6, 266-(y+3)*3)
    sheet.shape(box(*scheme['site']['parcel_bounds_m']), site_tr, 'none', '#7a8b91', '1,1')
    sheet.shape(box(0, 0, 18, 12), site_tr, '#e6edef', '#17313d')
    sheet.shape(box(*scheme['site']['side_escape_path_bounds_m']), site_tr, '#e2f3df', '#008575')
    sheet.line(*site_tr(-2, -3), *site_tr(20, -3), '#008575', .8)
    sheet.text(24, 273, 'South road edge | main forecourt and 1.50 m east path', 2.6)
    sheet.text(182, 222, 'Separate main and east exits on 1F, each 1.40 m clear.', 2.8)
    sheet.text(182, 229, 'Exterior ground and 1F finish proposed at z=+0.05 m.', 2.8)
    sheet.text(182, 236, 'Accessible WC: 2.60 x 2.55 m space reservation only.', 2.8)
    sheet.text(182, 243, 'Lift lobby: nominal 1.50 m turning circle shown.', 2.8)
    sheet.text(182, 250, 'Door leaves, fixtures and finished path continuity remain open.', 2.8, '#ad3724')
    sheet.write(out/'AH-002-layout.svg')

    sheet = Sheet('SH-002', 'Stair load path and vertical interface review', digest, 'H02')
    sheet.text(18, 37, 'Released gravity-strip proposal | diagram, not reinforcement detail', 3.4)
    tr2 = lambda y, z: (23+(y-5.5)*23, 175-z*10)
    for st, low, high in [('1F',0.,4.),('2F',4.,7.6),('3F',7.6,11.2)]:
        s = next(s for s in transfer['sources'] if s['source_name']==f'STF-{st}-A')
        points = s['components'][0]['support_reactions']
        a, b = points[0]['xyz_m'], points[2]['xyz_m']
        sheet.line(*tr2(a[1],low), *tr2(b[1],(low+high)/2), '#23556a', 1.)
        sheet.line(*tr2(b[1],(low+high)/2), *tr2(a[1],high), '#536d77', 1.)
        landing = next(s for s in transfer['sources'] if s['source_name']==f'STL-{st}-MID')
        obj = objects[landing['source_name']]
        y, z = landing['measure']['centroid_m'][1], obj['max'][2]
        sheet.line(*tr2(obj['min'][1],z), *tr2(obj['max'][1],z), '#23556a', 1.4)
        sheet.line(*tr2(y,z+1), *tr2(y,z), '#b44826', .65)
        sheet.text(*tr2(y+.1,z+.5), f"W at y={y:.2f}", 2.5)
        sheet.text(*tr2(5.5,high+.25), f'{high:.2f} SSL', 2.7)
    sheet.text(18, 188, 'Flights: actual centroid -> two end reactions -> transverse', 2.9)
    sheet.text(18, 194, 'landing strips -> west/shared walls -> trial fixed base.', 2.9)
    sheet.text(18, 200, 'Upper interface y=9.45 m; first-storey interface y=9.75 m.', 2.9)
    sheet.text(18, 206, 'Landings loaded at their own centroid, not the front edge.', 2.9)
    sheet.text(18, 212, 'Upper bearing overlap removed once; source solids unchanged.', 2.9)
    sheet.text(18, 218, 'Side-wall forces use exact first moments and mesh interpolation.', 2.9)
    sheet.text(18, 230, 'DESIGN HOLD: 180 mm landing flexure/shear and wall anchorage.', 2.9, '#ad3724')
    sheet.text(18, 236, 'End restraint, stair bracing, ground landing and joint steel open.', 2.9, '#ad3724')

    x = 220
    sheet.text(x, 37, 'Equipment and finished-core reservations', 3.4)
    lift = report['lift']
    notes = [
        'TMEC P10 / 700 kg / 2S / 60 m/min candidate.',
        'Cabin 1.20 x 1.45 m; clear door 0.90 m.',
        'Minimum finished shaft 1.80 x 1.90 m.',
        'Existing void 2.05 x 2.05 m; 10 mm finish/face assumed.',
        f"Nominal remaining margins {lift['nominal_dimension_margin_m'][0]:.2f} / {lift['nominal_dimension_margin_m'][1]:.2f} m.",
        'Margins are not a supplier fit or plumb-tolerance approval.',
        '', f"Lowest finished floor +0.05 -> pit floor {lift['pit_bottom_reservation_z_m']:.2f} m.",
        'Pit extends below -1.20 m diagnostic fixed base.',
        'Foundation interaction, waterproofing and buffers unresolved.',
        f"Highest stop +7.65 -> minimum overhead soffit +{lift['minimum_overhead_soffit_z_m']:.2f} m.",
        'Roof SSL +11.20: overrun needs new enclosed space.',
        'Roof stair enclosure: reserve 2.40 m above roof finish.',
        'Pit/headhouse are reservations, absent from source IFC.',
        'Equipment/enclosure loads have not entered this run.',
        '', f"Flight nominal finished width {report['stairs']['nominal_clear_flight_m']:.3f} m.",
        f"Central rail/guard nominal spare {report['stairs']['central_well_remaining_m']*1000:.0f} mm.",
        'Rail turn, brackets, tolerance and door swing not resolved.',
        'Upper fire door must open in escape direction into stair.',
        'Current 1.40 m front landing must be detailed together.',
        'Inter-storey riser mismatch remains a compliance hold.',
    ]
    for i, line in enumerate(notes): sheet.text(x, 46+i*6.6, line, 2.8)
    area = sum(s['horizontal_loaded_area_m2'] for s in transfer['sources'])
    removed = sum(s['measure']['upper_bearing_overlap_m3'] for s in transfer['sources'])
    sheet.text(18, 255, f'H02 quantity scope: {area:.2f} m2 stair finish/live projection; {removed:.4f} m3 overlapping concrete deducted.', 3.)
    sheet.text(18, 263, 'Reinforcement, formwork, foundations, equipment, enclosure and prices excluded; no cost saving claimed.', 2.9)
    sheet.write(out/'SH-002-transfer.svg')
    (out/'handoff-H02.html').write_text('<!doctype html><meta charset="utf-8"><title>H02 review</title>'
        '<style>@page{size:A3 landscape;margin:0}body{margin:0}svg{display:block;break-after:page;width:420mm;height:297mm}svg:last-child{break-after:auto}</style>'
        +''.join((out/name).read_text() for name in ('AH-002-layout.svg','SH-002-transfer.svg')))


def handoff_project(directory: Path, model_path: Path):
    directory, project, source, analysis, root = load_project(directory)
    if yaml.safe_load(analysis.read_text())['revision']!='H02':
        raise ValueError('The H02 handoff renderer cannot label a later model. Use the current core/interface review; see docs/development.md.')
    scheme_path = architectural_scheme(directory, project)
    model_path = model_path.resolve()
    if not model_path.is_relative_to(root/RUNS_RELATIVE) or model_path.name != 'analytical_model.json':
        raise ValueError('Handoff requires a recorded analytical build')
    parent = json.loads((model_path.parent/'manifest.json').read_text())
    if parent.get('task') != 'build' or parent.get('status') != 'COMPLETED_GEOMETRY_AND_ANALYSIS_INPUTS_ONLY':
        raise ValueError('Handoff requires a successfully completed build')
    verify_build_inputs(root, parent, (source, analysis, scheme_path))
    for name in ('analytical_model.json','stair_transfer.json'):
        if file_hash(model_path.parent/name) != parent['output_sha256'].get(name):
            raise ValueError('Build output changed before handoff; regenerate')
    run, manifest = make_run(root, project['id'], 'handoff')
    manifest['command'] = ['python','-m','structural_ai','handoff','--project',directory.relative_to(root).as_posix(),
                           '--model',model_path.relative_to(root).as_posix()]
    manifest['parent_build'] = parent['run_id']
    try:
        _, objects, _, _, _, levels = read_geometry(source)
        scheme = yaml.safe_load(scheme_path.read_text())
        transfer = json.loads((model_path.parent/'stair_transfer.json').read_text())
        report = proposal_checks(scheme, objects, levels)
        report.update(source_sha256=file_hash(source), scheme_sha256=file_hash(scheme_path),
                      analysis_sha256=file_hash(analysis), independent_geometry_objects_checked=len(objects))
        write_json(run/'handoff-review.json',report)
        with (run/'room-reservations.csv').open('w',newline='') as stream:
            writer=csv.writer(stream); writer.writerow(['id','name','planning_net_m2_per_level','levels','status'])
            for s in report['spaces']:
                writer.writerow([s['id'],s['name'],f"{s['planning_net_area_m2']:.6f}",'1F;2F;3F',s['scope']])
        draw_proposal(run,scheme,objects,levels,report,transfer,file_hash(source))
        finish_run(run,manifest,'COMPLETED_PROPOSAL_WITH_INTERFACE_HOLDS',exit_code=0,
                   architectural_acceptance=False,engineering_approval=False)
    except Exception:
        (run/'failure.txt').write_text(traceback.format_exc())
        finish_run(run,manifest,'FAILED',exit_code=1)
        raise
    return run
