"""A01 orthogonal wall/frame ownership and explicit monolithic joint inputs.

Columns and clear-span beam webs own their concrete before walls. Wall shells
represent the remaining thickness at its actual centroid. Physical IFC solids
are unchanged; the accounting partition is an analytical idealization.
"""
from collections import defaultdict
import numpy as np


def frame_bodies(products, geometry, model):
    bodies = []
    for name, product in products.items():
        if product.type not in ('IFCCOLUMN', 'IFCBEAM'):
            continue
        g = geometry[name]
        lo, hi = g['min'].copy(), g['max'].copy()
        reference = (lo + hi)/2
        role = 'column' if product.type == 'IFCCOLUMN' else 'beam'
        axis = 2
        if role == 'beam':
            axis = int(np.argmax((hi-lo)[:2]))
            reference[2] = hi[2]
            # A01 beams have a 0.18 m slab flange above the web.
            floor = [v for k, v in geometry.items() if products[k].type == 'IFCSLAB'
                     and k in ('S-2F', 'S-3F', 'S-RF') and abs(v['max'][2]-hi[2]) < 1e-7]
            if len(floor) != 1:
                raise ValueError('Beam must match one main-floor slab')
            hi[2] -= floor[0]['max'][2]-floor[0]['min'][2]
        bodies.append({'name': name, 'guid': product.args[0], 'role': role, 'axis': axis,
                       'lo': lo, 'hi': hi, 'reference': reference})
    return bodies


def wall_spec(geometry):
    lo, hi = geometry['min'], geometry['max']
    axis = int(np.argmax((hi-lo)[:2]))
    return {'axis': axis, 'normal': 1-axis, 'lo': lo, 'hi': hi}


def intervals(lo, hi, cuts):
    """Exact one-dimensional set subtraction, including overlapping owners."""
    result = [(float(lo), float(hi))]
    for a, b in cuts:
        updated = []
        for u, v in result:
            if b <= u+1e-10 or a >= v-1e-10:
                updated.append((u, v))
            else:
                if a > u+1e-10:
                    updated.append((u, min(a, v)))
                if b < v-1e-10:
                    updated.append((max(b, u), v))
        result = updated
    return result


def remaining_normal(spec, bodies, u, v, z1, z2):
    axis, normal = spec['axis'], spec['normal']
    cuts = []
    for body in bodies:
        if (body['lo'][axis] < (u+v)/2 < body['hi'][axis]
                and body['lo'][2] < (z1+z2)/2 < body['hi'][2]):
            if (u < body['lo'][axis]-1e-7 or v > body['hi'][axis]+1e-7
                    or z1 < body['lo'][2]-1e-7 or z2 > body['hi'][2]+1e-7):
                if min(body['hi'][normal], spec['hi'][normal]) > max(body['lo'][normal], spec['lo'][normal])+1e-8:
                    raise ValueError('Wall ownership mesh straddles a frame face')
            cuts.append((body['lo'][normal], body['hi'][normal]))
    return intervals(spec['lo'][normal], spec['hi'][normal], cuts)


def mesh_breaks(specs, bodies):
    """Include physical faces and every possible remaining-strip midplane."""
    result = [set(), set(), set()]
    for spec in specs.values():
        for axis in range(3):
            result[axis].update((float(spec['lo'][axis]), float(spec['hi'][axis])))
        normal = spec['normal']
        boundaries = {float(spec['lo'][normal]), float(spec['hi'][normal])}
        for body in bodies:
            if np.all(np.minimum(spec['hi'], body['hi'])-np.maximum(spec['lo'], body['lo']) > 1e-8):
                for axis in range(3):
                    result[axis].update((float(body['lo'][axis]), float(body['hi'][axis])))
                boundaries.update(float(p[normal]) for p in (body['lo'], body['hi'])
                                  if spec['lo'][normal] < p[normal] < spec['hi'][normal])
        values = sorted(boundaries)
        # Remaining intervals can combine adjacent subdivisions.
        result[normal].update((a+b)/2 for i, a in enumerate(values) for b in values[i+1:])
    return [sorted(values) for values in result]


def connect_interfaces(nodes, elements, specs, bodies, base_z):
    """Flatten short, physically justified rigid groups to one free master.

    Requests come from frame contact, wall thickness transitions and abutting
    perpendicular wall faces. Groups reaching multiple column stations within a
    beam depth form explicit rigid joint zones; their extents are reported.
    """
    xyz = {n['id']: np.array(n['xyz']) for n in nodes}
    coordinate_ids = {tuple(n['xyz']): n['id'] for n in nodes}
    wall_nodes = defaultdict(set)
    frame_nodes = defaultdict(set)
    column_nodes = set()
    for element in elements:
        if element['role'] == 'wall':
            wall_nodes[element['source_name']].update(element['nodes'])
        elif element['kind'] == 'frame':
            frame_nodes[element['source_name']].update(element['nodes'])
            if element['role'] == 'column':
                column_nodes.update(element['nodes'])
    parent = {node: node for node in xyz}
    reasons = []

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def join(a, b, reason, sources):
        if a == b:
            return
        parent[find(a)] = find(b)
        reasons.append({'nodes': [a, b], 'reason': reason, 'sources': list(sources)})

    def at(point):
        key = tuple(round(float(v), 10) for v in point)
        if key not in coordinate_ids:
            raise ValueError('Joint projection has no conforming frame node: '+str(key))
        return coordinate_ids[key]

    stations = {}
    continuous_stations = defaultdict(list)
    for name, node_set in wall_nodes.items():
        spec = specs[name]
        axis, normal = spec['axis'], spec['normal']
        station = defaultdict(list)
        for node in sorted(node_set):
            p = xyz[node]
            station[(round(float(p[axis]), 10), round(float(p[2]), 10))].append(node)
            for body in bodies:
                if (min(spec['hi'][normal], body['hi'][normal])-max(spec['lo'][normal], body['lo'][normal]) <= 1e-8
                        or not body['lo'][axis]-1e-7 <= p[axis] <= body['hi'][axis]+1e-7
                        or not body['lo'][2]-1e-7 <= p[2] <= body['hi'][2]+1e-7):
                    continue
                projection = body['reference'].copy()
                projection[body['axis']] = p[body['axis']]
                root = at(projection)
                if root not in frame_nodes[body['name']]:
                    raise ValueError('Projected master does not belong to the source frame')
                join(node, root, body['role']+'_wall_contact', (name, body['name']))
        for group in station.values():
            for node in group[1:]:
                join(group[0], node, 'wall_thickness_transition', (name,))
        stations[name] = station
        for key, group in station.items():
            continuous_stations[(name.rsplit('-',1)[0],*key)].extend((name,node) for node in group)

    for group in continuous_stations.values():
        for name,node in group[1:]:
            join(group[0][1],node,'wall_segment_transition',(group[0][0],name))

    for name, node_set in wall_nodes.items():
        spec = specs[name]
        axis = spec['axis']
        for other_name, other in specs.items():
            if other['axis'] == axis:
                continue
            for end in (spec['lo'][axis], spec['hi'][axis]):
                if min(abs(end-other['lo'][axis]), abs(end-other['hi'][axis])) > 1e-7:
                    continue
                for node in node_set:
                    p = xyz[node]
                    if abs(p[axis]-end) > 1e-7 or not other['lo'][2]-1e-7 <= p[2] <= other['hi'][2]+1e-7:
                        continue
                    key = (round(float(p[other['axis']]), 10), round(float(p[2]), 10))
                    for target in stations.get(other_name, {}).get(key, []):
                        join(node, target, 'abutting_wall_corner', (name, other_name))

    # Floor nodes inside a column footprint follow its cross-section. This also
    # makes any overlapping floor shell patch strain-free within the rigid joint.
    floor_nodes = {n for e in elements if e['role'] == 'floor' for n in e['nodes']}
    for node in floor_nodes:
        p = xyz[node]
        for body in bodies:
            if body['role'] == 'column' and np.all(p >= body['lo']-1e-7) and np.all(p <= body['hi']+1e-7):
                q = body['reference'].copy(); q[2] = p[2]
                root = at(q)
                join(node, root, 'column_floor_cross_section', (body['name'],))

    grouped = defaultdict(list)
    for node in xyz:
        grouped[find(node)].append(node)
    links, groups = [], []
    all_frame = set().union(*frame_nodes.values())
    for group in grouped.values():
        if len(group) < 2:
            continue
        points = np.array([xyz[node] for node in group])
        extent = np.ptp(points, axis=0)
        if np.any(extent > [.9, .9, .700001]):
            raise ValueError('Unexpectedly large rigid interface group: '+str(extent))
        fixed = [node for node in group if abs(xyz[node][2]-base_z) < 1e-7]
        if fixed:
            if len(fixed) != len(group):
                raise ValueError('A joint group crosses the trial support plane')
            groups.append({'nodes': sorted(group), 'status': 'DIRECT_BASE_FIXITY', 'extent_m': extent.tolist()})
            continue
        candidates = sorted(set(group)&column_nodes) or sorted(set(group)&all_frame) or sorted(group)
        master = min(candidates, key=lambda node: (-xyz[node][2], node))
        for slave in sorted(set(group)-{master}):
            links.append({'master': master, 'slave': slave, 'type': 'beam'})
        groups.append({'master': master, 'nodes': sorted(group), 'status': 'RIGID_SMALL_ROTATION',
                       'extent_m': extent.tolist(), 'column_node_count': len(set(group)&column_nodes)})
    return links, {'method': 'COLUMN_AND_BEAM_WEB_OWNED_CONCRETE_WITH_ECCENTRIC_RIGID_CONTACT',
                   'groups': groups, 'requests': reasons,
                   'scope': 'Gross elastic monolithic joint idealization; no bond slip, local shear flexibility, cracking or reinforcement acceptance'}
