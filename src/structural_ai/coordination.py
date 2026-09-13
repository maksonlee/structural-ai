"""A01 intake geometry and coordination sheets, not architectural or RC design.

The hash-guarded source uses axis-aligned prismatic solids and extruded stairs.
IfcOpenShell independently checks bounds/volumes and supplies net meshes. Nothing
here edits the IFC, analysis loads, sections or source-to-analysis mapping.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape
from pathlib import Path
import csv
import json
import traceback

import numpy as np
from shapely.geometry import Polygon, box
import yaml

from .cli import load_project
from .ifc_reader import Model
from .provenance import file_hash, make_run, finish_run, write_json


def volume_centroid(vertices, faces):
    """Signed tetrahedral integration over a closed, consistently oriented mesh."""
    triangles = np.asarray(vertices)[np.asarray(faces)]
    six_v = np.einsum('ij,ij->i', triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2]))
    total = float(six_v.sum())
    if not np.isfinite(total) or abs(total) < 1e-12:
        raise ValueError('Degenerate solid in coordination quantity screen')
    centre = np.sum(six_v[:, None] * triangles.sum(axis=1), axis=0) / (4 * total)
    return abs(total / 6), centre


def overhead_height(triangles, x, y, above):
    """Nearest triangle intersection above a vertical ray; None is missing overhead."""
    a, b, c = np.asarray(triangles).transpose(1, 0, 2)
    d = (b[:, 0]-a[:, 0])*(c[:, 1]-a[:, 1]) - (b[:, 1]-a[:, 1])*(c[:, 0]-a[:, 0])
    valid = abs(d) > 1e-12
    a, b, c, d = a[valid], b[valid], c[valid], d[valid]
    u = ((x-a[:, 0])*(c[:, 1]-a[:, 1]) - (y-a[:, 1])*(c[:, 0]-a[:, 0])) / d
    v = ((b[:, 0]-a[:, 0])*(y-a[:, 1]) - (b[:, 1]-a[:, 1])*(x-a[:, 0])) / d
    z = a[:, 2] + u*(b[:, 2]-a[:, 2]) + v*(c[:, 2]-a[:, 2])
    hits = z[(u >= -1e-8) & (v >= -1e-8) & (u+v <= 1+1e-8) & (z > above+1e-6)]
    return float(hits.min()) if len(hits) else None


def intersection_volume(a, b):
    return float(np.maximum(0, np.minimum(a['max'], b['max']) - np.maximum(a['min'], b['min'])).prod())


def read_geometry(source):
    try:
        import ifcopenshell
        import ifcopenshell.geom
    except ImportError as exc:
        raise RuntimeError('Coordination requires the ifc-validation extra in the project environment.') from exc
    subset = Model(source)
    native = ifcopenshell.open(str(source))
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    settings.set('disable-opening-subtractions', True)
    objects = {}
    meshes = {}
    geometry = {}
    for kind in ('IFCCOLUMN', 'IFCBEAM', 'IFCWALL', 'IFCSLAB', 'IFCSTAIRFLIGHT', 'IFCOPENINGELEMENT'):
        for e in subset.by_type(kind):
            name = e.args[2]
            g = subset.solid_geometry(e)
            shape = ifcopenshell.geom.create_shape(settings, native.by_id(e.id))
            vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
            faces = np.asarray(shape.geometry.faces).reshape(-1, 3)
            gross, _ = volume_centroid(vertices, faces)
            if not (np.allclose(vertices.min(0), g['min'], atol=1e-7, rtol=0)
                    and np.allclose(vertices.max(0), g['max'], atol=1e-7, rtol=0)
                    and np.isclose(gross, g['volume'], rtol=1e-7, atol=1e-8)):
                raise ValueError('Independent IFC geometry mismatch: ' + name)
            settings.set('disable-opening-subtractions', False)
            shape = ifcopenshell.geom.create_shape(settings, native.by_id(e.id))
            settings.set('disable-opening-subtractions', True)
            vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
            faces = np.asarray(shape.geometry.faces).reshape(-1, 3)
            net, centroid = volume_centroid(vertices, faces)
            objects[name] = {'name': name, 'guid': e.args[0], 'kind': kind, 'id': e.id,
                             'min': g['min'].tolist(), 'max': g['max'].tolist(),
                             'gross_m3': gross, 'net_m3': net, 'centroid_m': centroid.tolist()}
            geometry[name] = g
            meshes[name] = vertices[faces]
    holes = defaultdict(list)
    for rel in subset.by_type('IFCRELVOIDSELEMENT'):
        holes[subset[rel.args[4]].args[2]].append(subset[rel.args[5]].args[2])
    levels = {e.args[2]: float(e.args[-1]) for e in subset.by_type('IFCBUILDINGSTOREY')}
    return subset, objects, geometry, meshes, holes, levels


def screens(subset, objects, geometry, meshes, holes, levels, cfg):
    stairs, clearances, checks, landings = [], [], [], []
    rule = cfg['stairs']
    for e in subset.by_type('IFCSTAIRFLIGHT'):
        name = e.args[2]; o = objects[name]; g = geometry[name]
        width = o['max'][0] - o['min'][0]
        props = subset.psets(e)['A01_StairFlight']
        # For this source the ascending profile uses local x for run and y for rise.
        profile = g['profile']
        delta = np.diff(profile, axis=0)
        rises = delta[(abs(delta[:, 0]) < 1e-8) & (delta[:, 1] > 1e-8), 1]
        steps = [(p, q) for p, q in zip(profile, profile[1:])
                 if q[0] > p[0]+1e-8 and abs(q[1]-p[1]) < 1e-8 and p[1] < profile[:, 1].max()-1e-8]
        if len(rises) != e.args[8] or len(steps) != e.args[9] or not np.allclose(rises, e.args[10], atol=1e-8):
            raise ValueError('Stair profile and riser attributes disagree: ' + name)
        depths = [q[0]-p[0] for p, q in steps]
        if not np.allclose(depths, e.args[11], atol=1e-8):
            raise ValueError('Stair profile and tread attributes disagree: ' + name)
        row = dict(name=name, guid=o['guid'], risers=len(rises), treads=len(steps),
                   riser_m=float(max(rises)), tread_m=float(min(depths)), rough_width_m=width,
                   target_finished_width_m=props['TargetFinishedClearWidth_m'])
        row['width_scenarios'] = []
        for extra in rule['finish_allowance_extra_scenarios_m']:
            allowance = props['HandrailAndFinishAllowanceTotal_m'] + extra
            clear = width - allowance
            row['width_scenarios'].append({'total_allowance_m': allowance, 'clear_width_m': clear,
                'margin_to_project_target_m': clear-row['target_finished_width_m'],
                'status': 'MEETS_TARGET_IF_ALLOWANCE_SUFFICIENT' if clear+1e-8 >= row['target_finished_width_m'] else 'BELOW_PROJECT_TARGET'})
        stairs.append(row)
        for scenario in rule['conventional_scenarios']:
            checks.append({'id': name+'-'+scenario['id'], 'guid': o['guid'], 'source_id': cfg['screen_basis']['source_id'],
                'clause': scenario['clause'], 'condition': scenario['condition'], 'units': 'm',
                'riser_input': row['riser_m'], 'riser_limit': scenario['riser_max_m'],
                'tread_input': row['tread_m'], 'tread_limit': scenario['tread_min_m'],
                'width_limit': scenario['width_min_m'], 'finished_width_status': 'NOT_CHECKED',
                'status': 'WITHIN_RAW_RISER_TREAD_LIMITS' if row['riser_m'] <= scenario['riser_max_m']+1e-8 and row['tread_m'] >= scenario['tread_min_m']-1e-8 else 'OUTSIDE_RAW_RISER_TREAD_LIMITS'})
        a = rule['accessible']; comfort = 2*row['riser_m']+row['tread_m']
        checks.append({'id': name+'-ACCESSIBLE-304.1', 'guid': o['guid'], 'source_id': a['source_id'],
            'clause': a['clause'], 'units': 'm', 'riser_input': row['riser_m'], 'riser_limit': a['riser_max_m'],
            'tread_input': row['tread_m'], 'tread_limit': a['tread_min_m'], 'two_risers_plus_tread': comfort,
            'allowed_range': a['two_risers_plus_tread_range_m'],
            'status': 'WITHIN_INDIVIDUAL_FLIGHT_RAW_LIMITS' if row['riser_m'] <= a['riser_max_m']+1e-8 and row['tread_m'] >= a['tread_min_m']-1e-8 and a['two_risers_plus_tread_range_m'][0] <= comfort <= a['two_risers_plus_tread_range_m'][1] else 'OUTSIDE_INDIVIDUAL_FLIGHT_RAW_LIMITS'})
        # Evaluate every actual tread nosing, at three positions across its width.
        samples = []
        for p, q in steps:
            local = [p[0], p[1], 0, 1]
            world = g['matrix'] @ local
            for x in np.linspace(o['min'][0]+.002, o['max'][0]-.002, rule['headroom_samples_across_width']):
                candidates = []
                for other, triangles in meshes.items():
                    if other == name or objects[other]['kind'] == 'IFCOPENINGELEMENT': continue
                    hit = overhead_height(triangles, x, world[1], world[2])
                    if hit is not None: candidates.append((hit-world[2], other))
                gap, overhead = min(candidates) if candidates else (None, None)
                samples.append({'point_m': [float(x), float(world[1]), float(world[2])], 'gap_m': gap, 'overhead': overhead})
        finite = [s for s in samples if s['gap_m'] is not None]
        clearances.append({'name': name, 'guid': o['guid'], 'samples': samples,
            'minimum_raw_gap_m': min((s['gap_m'] for s in finite), default=None),
            'missing_overhead_samples': len(samples)-len(finite), 'status': 'RAW_NOSING_SCREEN_ONLY',
            'final_code_status': rule['headroom']['final_status']})
    for name, o in objects.items():
        if not name.startswith('STL-'): continue
        storey = name.split('-')[1]
        flights = [s for s in stairs if s['name'].startswith('STF-'+storey+'-')]
        depth = o['max'][1]-o['min'][1]
        landings.append({'name': name, 'guid': o['guid'], 'depth_m': depth,
                         'flight_interface_y_m': o['min'][1], 'centroid_y_m': o['centroid_m'][1],
                         'adjacent_flight_width_m': max(s['rough_width_m'] for s in flights),
                         'raw_depth_margin_m': depth-max(s['rough_width_m'] for s in flights),
                         'status': 'RAW_GEOMETRY_ONLY_TURNING_AND_FINISHES_OPEN'})
    clashes = [{'beam': b['name'], 'beam_guid': b['guid'], 'opening': o['name'], 'opening_guid': o['guid'],
                'intersection_m3': intersection_volume(b, o)}
               for b in objects.values() if b['kind'] == 'IFCBEAM'
               for o in objects.values() if o['kind'] == 'IFCOPENINGELEMENT' and intersection_volume(b, o) > 1e-8]
    floors = []
    for level, z in levels.items():
        slab = objects['S-'+level]
        floors.append({'level': level, 'structural_top_m': z, 'guid': slab['guid'],
                       'gross_projection_m2': (slab['max'][0]-slab['min'][0])*(slab['max'][1]-slab['min'][1]),
                       'net_slab_projection_m2': slab['net_m3']/(slab['max'][2]-slab['min'][2]),
                       'occupied_room_area_m2': None, 'statutory_floor_area_m2': None,
                       'ceiling_mep_and_finish_status': 'NOT_DEFINED'})
    return {'stairs': stairs, 'landings': landings, 'stair_headroom': clearances,
            'dimension_checks': checks, 'beam_opening_intersections': clashes, 'floors': floors,
            'inter_storey_riser_uniformity': 'REQUIRES_REVIEW' if np.ptp([s['riser_m'] for s in stairs]) > 1e-8 else 'RAW_VALUES_EQUAL',
            'whole_route_code_status': 'NOT_CHECKED'}


class Sheet:
    """A3 vector drawing in millimetres; no external fonts, scripts or assets."""
    def __init__(self, number, title, digest, revision='H01', source_label='structural.ifc R05'):
        self.parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297">',
                      '<rect width="420" height="297" fill="white"/>',
                      '<style>text{font-family:Arial,sans-serif;fill:#17313d} .small{font-size:2.4px}</style>']
        self.rect(8, 8, 404, 281, 'none', '#17313d', .35)
        self.text(14, 19, number+'  '+title, 5)
        self.text(14, 25, f'SIMULATED COORDINATION REVIEW {revision} | NOT FOR CONSTRUCTION | 2026-09-13', 2.8, '#aa3a20')
        self.line(8, 278, 412, 278)
        self.text(14, 283, 'Source: '+source_label+' | SHA256 '+digest[:20]+'... | units: m unless stated', 2.5)
        self.text(14, 287, 'Retained structural scheme; architectural package, finishes, reinforcement and foundation design remain open.', 2.4)

    def text(self, x, y, value, size=2.8, colour='#17313d'):
        self.parts.append(f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" style="fill:{colour}">{escape(str(value))}</text>')

    def line(self, x1, y1, x2, y2, colour='#80949c', width=.2, dash=''):
        self.parts.append(f'<path d="M{x1:.3f},{y1:.3f} L{x2:.3f},{y2:.3f}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-dasharray="{dash}"/>')

    def rect(self, x, y, w, h, fill, stroke='#80949c', width=.2):
        self.parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')

    def shape(self, polygon, transform, fill, stroke, dash='', guid=None):
        if polygon.is_empty: return
        if polygon.geom_type != 'Polygon':
            for part in polygon.geoms: self.shape(part, transform, fill, stroke, dash, guid)
            return
        d = []
        for ring in [polygon.exterior, *polygon.interiors]:
            points = [transform(x, y) for x, y in ring.coords]
            d.append('M'+' L'.join(f'{x:.3f},{y:.3f}' for x, y in points)+' Z')
        tag = f' data-source-guid="{escape(guid)}"' if guid else ''
        self.parts.append(f'<path d="{" ".join(d)}" fill="{fill}" fill-rule="evenodd" stroke="{stroke}" stroke-width=".25" stroke-dasharray="{dash}"{tag}/>')

    def write(self, path):
        path.write_text('\n'.join([*self.parts, '</svg>'])+'\n', encoding='utf-8')


def projected_beams(objects, levels, level):
    """Plan beams above the occupied level; the roof view uses beams at its slab."""
    z = levels[level]
    top = min((height for height in levels.values() if height > z+1e-8), default=z)
    return [o for o in objects.values() if o['kind']=='IFCBEAM' and abs(o['max'][2]-top)<1e-8]


def drawings(out, source_hash, subset, objects, geometry, holes, levels, report):
    colours = {'IFCSLAB': '#eef3f4', 'IFCWALL': '#8fadb5', 'IFCCOLUMN': '#385b68', 'IFCBEAM': '#e5eefb', 'IFCSTAIRFLIGHT': '#d9ece4'}
    plans = Sheet('CO-001', 'Whole-building structural reference plans', source_hash)
    columns = [o for o in objects.values() if o['kind'] == 'IFCCOLUMN' and o['name'].endswith('-1F')]
    gridx = sorted({round((o['min'][0]+o['max'][0])/2, 6) for o in columns})
    gridy = sorted({round((o['min'][1]+o['max'][1])/2, 6) for o in columns})
    for index, (level, z) in enumerate(levels.items()):
        ox, oy = 24 + (index % 2)*190, 139 + (index//2)*118
        transform = lambda x, y: (ox+x*8, oy-y*8)
        plans.text(ox-10, oy-103, f'{level} | structural top {z:.2f} | 1:125 at A3', 3.3)
        slab = objects['S-'+level]
        polygon = box(*slab['min'][:2], *slab['max'][:2])
        for hole in holes.get(slab['name'], []):
            h = objects[hole]; polygon = polygon.difference(box(*h['min'][:2], *h['max'][:2]))
        plans.shape(polygon, transform, colours['IFCSLAB'], '#80949c', guid=slab['guid'])
        outgoing = level if level != 'RF' else '3F'
        beam_names={o['name'] for o in projected_beams(objects,levels,level)}
        for name, o in objects.items():
            if o['kind'] in ('IFCCOLUMN', 'IFCWALL') and name.endswith('-'+outgoing):
                poly = box(*o['min'][:2], *o['max'][:2])
                # The wall plan cut is 1 m above the referenced storey; cut door voids.
                for hole in holes.get(name, []):
                    h=objects[hole]
                    if h['min'][2] < levels[outgoing]+1 < h['max'][2]:
                        poly=poly.difference(box(*h['min'][:2], *h['max'][:2]))
                plans.shape(poly, transform, colours[o['kind']], '#385b68', guid=o['guid'])
            if name in beam_names:
                plans.shape(box(*o['min'][:2], *o['max'][:2]), transform, 'none', '#6686ac', '1,.7', o['guid'])
            if name=='STL-'+outgoing+'-MID':
                plans.shape(box(*o['min'][:2], *o['max'][:2]), transform, colours['IFCSTAIRFLIGHT'], '#398365', guid=o['guid'])
            if name.startswith('STF-'+outgoing+'-'):
                plans.shape(box(*o['min'][:2], *o['max'][:2]), transform, colours['IFCSTAIRFLIGHT'], '#398365', guid=o['guid'])
                g=geometry[name]
                for p, q in zip(g['profile'], g['profile'][1:]):
                    if abs(q[0]-p[0])<1e-8 and q[1]>p[1]:
                        point=g['matrix']@np.array([p[0],q[1],0,1])
                        a,b=transform(o['min'][0],point[1]),transform(o['max'][0],point[1])
                        plans.line(*a,*b,'#398365',.15)
        for label,x in zip('ABCD',gridx):
            plans.line(*transform(x,-.6),*transform(x,12.6),'#a6b4ba',.12,'1,1')
            plans.text(ox+x*8-1,oy+5,label,2.6)
        for left,right in zip(gridx,gridx[1:]):
            plans.line(*transform(left,12.3),*transform(right,12.3),'#80949c',.15)
            plans.text(ox+(left+right)*4-3,oy-12.5*8,f'{right-left:.2f}',2.2)
        for label,y in enumerate(gridy,1):
            plans.line(*transform(-.6,y),*transform(18.6,y),'#a6b4ba',.12,'1,1')
            plans.text(ox-5,oy-y*8+1,label,2.6)
        plans.text(ox+148,oy-90,'Y+',2.5)
        plans.text(ox+148,oy-85,'not north',2.3)
        plans.text(ox+148,oy-70,'B2 / C2',2.5)
        plans.text(ox+148,oy-65,'retained',2.5)
        plans.text(ox+148,oy-50,'rear span',2.5)
        plans.text(ox+148,oy-45,f'{gridy[-1]-gridy[-2]:.2f} m',2.5)
        plans.text(ox-10,oy+7,'Solid: structure / stair projection. Dashed: beams at roof slab.' if level=='RF' else 'Solid: structure / stair projection. Dashed: beams above.',2.3)
        plans.text(ox-10,oy+11,'RF shows structure below; roof enclosure/equipment are absent.' if level=='RF' else 'Room layout, exterior doors and finished egress paths are undefined.',2.3)
    plans.text(14,272,'Review references: CR-01 site/rooms | CR-02 fire/access | CR-03 stairs | CR-04 lift/roof | CR-05 load transfer',2.6)
    plans.write(out/'CO-001-plans.svg')
    sections=Sheet('CO-002','Stair sections and interface review',source_hash)
    for i,suffix in enumerate(('A','B')):
        obj=objects['STF-1F-'+suffix];x=(obj['min'][0]+obj['max'][0])/2
        ox=20+i*124; oy=235; scale=14
        tr=lambda y,z:(ox+(y-4)*scale,oy-z*scale)
        sections.text(ox,37,f'Section {suffix} | x={x:.3f} m | 1:{1000/scale:.2f}',3.3)
        for name,o in objects.items():
            if o['kind']=='IFCOPENINGELEMENT' or not o['min'][0]+1e-8<x<o['max'][0]-1e-8:continue
            if o['kind']=='IFCSTAIRFLIGHT':
                g=geometry[name];poly=Polygon(g['vertices'][:len(g['profile'])][:,[1,2]])
            else:poly=box(o['min'][1],o['min'][2],o['max'][1],o['max'][2])
            for hole in holes.get(name,[]):
                h=objects[hole]
                if h['min'][0]<x<h['max'][0]:poly=poly.difference(box(h['min'][1],h['min'][2],h['max'][1],h['max'][2]))
            poly=poly.intersection(box(4,-.25,12,12))
            sections.shape(poly,tr,colours[o['kind']],'#385b68',guid=o['guid'])
        for level,z in levels.items():
            sections.line(*tr(4,z),*tr(12,z),'#a6b4ba',.12,'1,1')
            sections.text(ox,oy-z*scale-1,level+' '+f'{z:.2f}',2.5)
        for row in report['landings']:
            o=objects[row['name']];point=tr(row['flight_interface_y_m'],o['max'][2])
            sections.line(point[0],point[1],point[0],point[1]-6,'#ae492c',.4)
            sections.text(point[0]-10,point[1]-8,f'y={row["flight_interface_y_m"]:.2f}',2.5,'#ae492c')
        sections.text(ox,250,'Actual stepped profiles and represented slab voids.',2.4)
        sections.text(ox,255,'Connections shown geometrically; anchorage is undesigned.',2.4)
    stair=report['stairs'][0]; baseline, sensitivity=stair['width_scenarios']
    shaft=objects['OPEN-LIFT-1F']; door=objects['OPEN-LIFT-DOOR-1F']
    upper=report['landings'][1]
    notes=[
        'CR-03  FINISHED STAIR WIDTH',
        f'Source rough width: {stair["rough_width_m"]:.2f} m.',
        f'IFC allowance: {baseline["total_allowance_m"]:.2f} m -> {baseline["clear_width_m"]:.2f} m.',
        f'Allowance {sensitivity["total_allowance_m"]:.2f} m -> {sensitivity["clear_width_m"]:.2f} m: review target.',
        'Check rails, finishes, door swings and turns.',
        '', 'CR-05  TRANSFER STATIONS',
        f'Upper landing starts: y={upper["flight_interface_y_m"]:.2f} m.',
        'See CR-05 for inherited load stations.',
        'Landing centroid and support design also matter.',
        'No load-path or anchorage acceptance implied.',
        '', 'CR-04  LIFT / ROOF',
        f'Shaft void: {shaft["max"][0]-shaft["min"][0]:.2f} x {shaft["max"][1]-shaft["min"][1]:.2f} m.',
        f'Rough lift door: {door["max"][0]-door["min"][0]:.2f} x {door["max"][2]-door["min"][2]:.2f} m.',
        'Pit, overrun, headhouse and reactions missing.',
        '', 'CR-02  FIRE / ACCESS',
        'Safety-stair enclosure and doors require details.',
        'Accessible route / WC / finishes unresolved.',
        'RF flights have no represented overhead roof.',
        '', 'COST / CONSTRUCTION',
        'Retain main frame while resolving interfaces.',
        'Compare wall anchorage / landing support options.',
        'No budget or complete bill of quantities.',
    ]
    for j,text in enumerate(notes):sections.text(272,40+j*7,text,2.6)
    sections.write(out/'CO-002-sections.svg')
    # Standalone print view; SVGs are vector artifacts, not an application.
    body=''.join('<section>'+p.read_text()+'</section>' for p in (out/'CO-001-plans.svg',out/'CO-002-sections.svg'))
    (out/'coordination.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>CO-001 coordination review</title><style>@page{size:A3 landscape;margin:0}body{margin:0;background:#e6ecee}section{width:420mm;height:297mm;background:white;break-after:page}section:last-child{break-after:auto}svg{display:block}</style><body>'+body+'</body></html>')


def coordinate_project(directory: Path):
    directory, project, source, analysis, root = load_project(directory)
    if yaml.safe_load(analysis.read_text())['revision']=='H03-C':
        raise ValueError('The H01 coordinate renderer is historical. Use core-review and the current H03-C interface review; see docs/development.md.')
    cfg_path = (directory/project['inputs']['coordination']).resolve()
    if not cfg_path.is_relative_to(directory): raise ValueError('Coordination input must remain inside project')
    cfg = yaml.safe_load(cfg_path.read_text())
    handoff = (cfg_path.parent/cfg['handoff']).resolve()
    if not handoff.is_relative_to(directory): raise ValueError('Handoff must remain inside project')
    brief = yaml.safe_load(handoff.read_text())
    run, manifest = make_run(root, project['id'], 'coordination')
    manifest['command'] = ['python','-m','structural_ai','coordinate','--project',directory.relative_to(root).as_posix()]
    try:
        subset, objects, geometry, meshes, holes, levels = read_geometry(source)
        report = screens(subset,objects,geometry,meshes,holes,levels,cfg)
        report.update(review_id=cfg['review_id'], handoff_id=brief['id'], handoff_revision=brief['revision'],
                      source_sha256=file_hash(source), analysis_sha256=file_hash(analysis),
                      handoff_sha256=file_hash(handoff), coordination_input_sha256=file_hash(cfg_path),
                      objects=list(objects.values()), independent_geometry_objects_checked=len(objects),
                      engineering_approval=False, analysis_inputs_changed=False, final_design_complete=False)
        write_json(run/'coordination-review.json',report)
        with (run/'physical-quantities.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['guid','name','kind','net_individual_solid_m3','scope'])
            for o in objects.values():
                if o['kind']!='IFCOPENINGELEMENT':writer.writerow([o['guid'],o['name'],o['kind'],f'{o["net_m3"]:.9f}','SOURCE_ONLY; INTER_MEMBER_OVERLAPS_NOT_RECONCILED; NOT_A_BOQ'])
        drawings(run,file_hash(source),subset,objects,geometry,holes,levels,report)
        finish_run(run,manifest,'COMPLETED_COORDINATION_REVIEW_WITH_OPEN_ITEMS',exit_code=0,
                   independent_geometry_checked=True,solver_executed=False,architectural_acceptance=False)
    except Exception:
        (run/'failure.txt').write_text(traceback.format_exc())
        finish_run(run,manifest,'FAILED',exit_code=1)
        raise
    return run
