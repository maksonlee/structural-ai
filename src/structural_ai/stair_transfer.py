"""Case-specific released stair gravity strips; no stair stiffness or RC design.

See project/structural/design/stair-load-method.md for support and quantity scope.
The IFC's stepped profile, receiving slab and side-wall midplanes are authorities.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon, box, LineString


def reactions(weight, centroid, a, b):
    """Two vertical reactions from force and first-moment equilibrium."""
    if not np.isfinite([weight, centroid, a, b]).all() or weight < 0 or b <= a:
        raise ValueError('Invalid released strip inputs')
    ratio = (centroid-a)/(b-a)
    if ratio < -1e-8 or ratio > 1+1e-8:
        raise ValueError('Resultant is outside the proposed strip supports')
    ratio = min(1., max(0., ratio))
    return [weight*(1-ratio), weight*ratio]


def plane_weights(nodes, point, axis=0):
    """Positive bilinear weights on an existing complete planar node cell.

    Fail on missing corners or out-of-plane/out-of-grid points. Never create a
    disconnected node or snap a load to the closest node. Caller supplies only
    nodes of the receiving continuous side wall, not all nodes with equal x.
    """
    point = np.asarray(point, dtype=float)
    if not np.isfinite(point).all() or not nodes:
        raise ValueError('Invalid wall station')
    if any(abs(n['xyz'][axis]-point[axis]) > 1e-6 for n in nodes):
        raise ValueError('Station is not on the receiving wall plane')
    indices = [i for i in range(3) if i != axis]
    brackets = []
    for i in indices:
        values = sorted(set(float(n['xyz'][i]) for n in nodes))
        close = [v for v in values if abs(v-point[i]) < 1e-7]
        if close:
            brackets.append([(close[0], 1.)])
            continue
        lower, upper = [v for v in values if v < point[i]], [v for v in values if v > point[i]]
        if not lower or not upper:
            raise ValueError('Station outside the receiving wall grid')
        a, b = lower[-1], upper[0]
        brackets.append([(a, (b-point[i])/(b-a)), (b, (point[i]-a)/(b-a))])
    result = []
    for a, wa in brackets[0]:
        for b, wb in brackets[1]:
            matches = [n for n in nodes if abs(n['xyz'][indices[0]]-a) < 1e-7
                       and abs(n['xyz'][indices[1]]-b) < 1e-7]
            if len(matches) != 1:
                raise ValueError('Missing or duplicate wall grid corner')
            result.append((matches[0]['id'], wa*wb))
    return result


def flight_measure(model, entity, host, host_holes):
    """Integrate an x-extruded flight, deducting its upper receiving slab overlap."""
    g = model.solid_geometry(entity)
    vertices = g['vertices']
    count = len(g['profile'])
    delta = vertices[count:]-vertices[:count]
    if not (np.allclose(delta[:, 1:], 0, atol=1e-8)
            and np.allclose(abs(delta[:, 0]), g['max'][0]-g['min'][0])):
        raise ValueError('Stair converter requires source-reviewed x extrusion')
    section = Polygon(vertices[:count, 1:])
    width = float(g['max'][0]-g['min'][0])
    hg = model.solid_geometry(host)
    if hg['min'][0] > g['min'][0]+1e-8 or hg['max'][0] < g['max'][0]-1e-8:
        raise ValueError('Partial-width upper stair bearing requires converter review')
    if 'A01_H03_Stair' in model.psets(entity):
        from .core_revision import horizontal_polygon
        footprint=horizontal_polygon(hg)
        for hole in host_holes:footprint=footprint.difference(horizontal_polygon(model.solid_geometry(hole)))
        polygons=list(footprint.geoms) if footprint.geom_type=='MultiPolygon' else [footprint]
        cuts={float(g['min'][0]),float(g['max'][0])}
        for polygon in polygons:
            for ring in [polygon.exterior,*polygon.interiors]:
                cuts.update(float(x) for x,y in ring.coords if g['min'][0]<x<g['max'][0])
        cuts=sorted(cuts);volume=overlap_volume=0.;moment=np.zeros(3)
        for xa,xb in zip(cuts,cuts[1:]):
            xm=(xa+xb)/2
            cut=footprint.intersection(LineString([(xm,-100),(xm,100)]))
            segments=list(cut.geoms) if hasattr(cut,'geoms') else [cut]
            net=section
            for segment in segments:
                if segment.is_empty or segment.geom_type!='LineString':continue
                lo,hi=segment.bounds[1],segment.bounds[3]
                net=net.difference(box(lo,hg['min'][2],hi,hg['max'][2]))
            dv=net.area*(xb-xa);volume+=dv;overlap_volume+=(section.area-net.area)*(xb-xa)
            moment+=dv*np.array([xm,net.centroid.x,net.centroid.y])
        if volume<=0:raise ValueError('Stair has no owned volume after bearing subtraction')
        return {'gross_volume_m3':float(section.area*width),'owned_volume_m3':float(volume),
                'upper_bearing_overlap_m3':float(overlap_volume),'centroid_m':(moment/volume).tolist(),
                'gross_centroid_m':[float((g['min'][0]+g['max'][0])/2),float(section.centroid.x),float(section.centroid.y)],
                'receiving_slab':host.args[2],'width_m':width,'method':'Exact x-strip integration against actual receiving footprint and voids'}
    receiving = box(hg['min'][1], hg['min'][2], hg['max'][1], hg['max'][2])
    for hole in host_holes:
        h = model.solid_geometry(hole)
        if h['max'][0] <= g['min'][0]+1e-8 or h['min'][0] >= g['max'][0]-1e-8:
            continue
        if h['min'][0] > g['min'][0]+1e-8 or h['max'][0] < g['max'][0]-1e-8:
            raise ValueError('Partial-width stair opening requires converter review')
        receiving = receiving.difference(box(h['min'][1], h['min'][2], h['max'][1], h['max'][2]))
    overlap = section.intersection(receiving)
    net = section.difference(receiving)
    if not net.is_valid or net.is_empty:
        raise ValueError('Invalid stair net section')
    x = float((g['min'][0]+g['max'][0])/2)
    return {'gross_volume_m3': float(section.area*width),
            'owned_volume_m3': float(net.area*width),
            'upper_bearing_overlap_m3': float(overlap.area*width),
            'centroid_m': [x, float(net.centroid.x), float(net.centroid.y)],
            'gross_centroid_m': [x, float(section.centroid.x), float(section.centroid.y)],
            'receiving_slab': host.args[2], 'width_m': width}


def apply_stairs(model, products, geometry, voids, nodes, elements, loads, masses,
                 ledger, gamma, grav, live_pressure, finish_pressure, owned_wall_cells=False):
    """Apply source-derived gravity/mass with auditable load-only mappings."""
    if not np.isfinite([gamma, grav, live_pressure, finish_pressure]).all() or min(
            gamma, grav, live_pressure, finish_pressure) <= 0:
        raise ValueError('Positive finite stair weights required')
    node_map = {n['id']: n for n in nodes}
    side_nodes = []
    side_x = []
    side_cells = []
    for prefix in ('SW-STAIR-W', 'SW-SHARED-STAIR-LIFT'):
        ids = {n for e in elements if e['source_name'].rsplit('-', 1)[0] == prefix for n in e['nodes']}
        subset = [node_map[n] for n in sorted(ids)]
        g = geometry[prefix+'-1F']
        x = float((g['min'][0]+g['max'][0])/2)
        if not subset or (not owned_wall_cells and any(abs(n['xyz'][0]-x) > 1e-7 for n in subset)):
            raise ValueError('Side-wall source/midplane mapping changed')
        if owned_wall_cells and any(not g['min'][0]-1e-7 <= n['xyz'][0] <= g['max'][0]+1e-7 for n in subset):
            raise ValueError('Owned wall midplane lies outside the physical source')
        side_x.append(x)
        side_nodes.append(subset)
        side_cells.append([e for e in elements if e['source_name'].rsplit('-', 1)[0] == prefix])
    records = []

    def apply(name, measure, stations, area, area_centroid):
        components = []
        for case, weight, centroid, add_mass in (
                ('D_SELF', measure['owned_volume_m3']*gamma, measure['centroid_m'], True),
                ('D_SUPER', area*finish_pressure, area_centroid, True),
                ('L_STAIRS', area*live_pressure, area_centroid, False)):
            if len(stations) == 2:
                a, b = stations
                values = reactions(weight, centroid[1], a[0], b[0])
                support_points = [(y, z, w) for (y, z), w in zip(stations, values)]
            else:
                support_points = [(centroid[1], stations[0][1], weight)]
            transfers = []
            nodal = {}
            for y, z, w in support_points:
                selections=[]
                for nominal_x, wall_nodes, cells in zip(side_x, side_nodes, side_cells):
                    if owned_wall_cells:
                        candidates=[]
                        for cell in cells:
                            corners=[node_map[n] for n in cell['nodes']]
                            coords=np.array([n['xyz'] for n in corners])
                            if np.all([y,z]>=coords[:,1:].min(0)-1e-7) and np.all([y,z]<=coords[:,1:].max(0)+1e-7):
                                candidates.append((abs(coords[0,0]-nominal_x),cell['id'],float(coords[0,0]),corners))
                        if not candidates:
                            raise ValueError('Stair station has no owned wall cell; support revision required')
                        _,_,x,selected=min(candidates,key=lambda item:item[:2])
                        selections.append((x,plane_weights(selected,[x,y,z])))
                    else:
                        selections.append((nominal_x,plane_weights(wall_nodes,[nominal_x,y,z])))
                for (x,weights),r in zip(selections,reactions(w,centroid[0],*[s[0] for s in selections])):
                    for nid, factor in weights:
                        value = r*factor
                        nodal[nid] = nodal.get(nid, 0.)+value
                    transfers.append({'xyz_m': [x, y, z], 'downward_kN': r})
            for nid, w in nodal.items():
                loads[case][nid][2] -= w
                if add_mass:
                    masses[nid] += w/grav
            actual = sum((np.array([-w, -w*node_map[n]['xyz'][1], w*node_map[n]['xyz'][0]])
                          for n, w in nodal.items()), start=np.zeros(3))
            expected = np.array([-weight, -weight*centroid[1], weight*centroid[0]])
            error = float(max(abs(actual-expected)))
            if error > 1e-7:
                raise ValueError('Stair transfer lost force or horizontal first moment')
            components.append({'case': case, 'weight_kN': weight, 'physical_centroid_m': centroid,
                               'support_reactions': transfers,
                               'receiving_nodes': [{'node': n, 'downward_kN': w} for n, w in sorted(nodal.items())],
                               'Fz_Mx_My_residual_max_kN_kNm': error,
                               'equivalent_mass_centroid_z_m': sum(w*node_map[n]['xyz'][2] for n, w in nodal.items())/weight if add_mass else None})
        record = {'source_name': name, 'source_guid': products[name].args[0],
                  'role': 'LOAD_ONLY_RELEASED_STRIPS_NOT_RC_DESIGN', 'measure': measure,
                  'horizontal_loaded_area_m2': area, 'components': components}
        records.append(record)
        ledger.append({'source': name, 'self_weight_kN': measure['owned_volume_m3']*gamma,
                       'note': 'Released gravity strips; upper bearing overlap owned by receiving slab; see stair_transfer.json'})

    for st, upper in [('1F', '2F'), ('2F', '3F'), ('3F', 'RF')]:
        landing = products[f'STL-{st}-MID']
        lg = geometry[landing.args[2]]
        floor = products['S-'+upper]
        fg = geometry[floor.args[2]]
        if 'A01_H03_Stair' in model.psets(products['STF-'+st+'-A']):
            from .core_revision import horizontal_polygon
            for suffix,host in [('A',landing),('B',floor)]:
                name=f'STF-{st}-{suffix}';entity=products[name];props=model.psets(entity)['A01_H03_Stair']
                measure=flight_measure(model,entity,host,[products[n] for n in voids[host.args[2]]])
                stations=sorted([(props['LowerSupportY_m'],props['LowerSupportZ_m']),
                                 (props['UpperSupportY_m'],props['UpperSupportZ_m'])])
                span=stations[1][0]-stations[0][0]
                if abs(span-(entity.args[8]-1)*entity.args[11])>1e-7:raise ValueError('Source support/nosing run mismatch')
                area=measure['width_m']*span
                apply(name,measure,stations,area,[measure['centroid_m'][0],sum(y for y,z in stations)/2,sum(z for y,z in stations)/2])
            poly=horizontal_polygon(lg);centre=[poly.centroid.x,poly.centroid.y,float((lg['min'][2]+lg['max'][2])/2)]
            measure={'gross_volume_m3':float(lg['volume']),'owned_volume_m3':float(lg['volume']),
                     'upper_bearing_overlap_m3':0.,'centroid_m':centre}
            apply(landing.args[2],measure,[(centre[1],float(lg['max'][2]))],poly.area,[*centre[:2],float(lg['max'][2])])
            continue
        stair_holes = [products[n] for n in voids[floor.args[2]] if 'STAIR' in n]
        if len(stair_holes) != 1:
            raise ValueError('Expected one source stair opening on the receiving floor')
        front_y = float(geometry[stair_holes[0].args[2]]['min'][1])
        mid_y, mid_z, top_z = float(lg['min'][1]), float(lg['max'][2]), float(fg['max'][2])
        lower_z = float(geometry['S-'+st]['max'][2])
        for suffix, host, stations in (
                ('A', landing, [(front_y, lower_z), (mid_y, mid_z)]),
                ('B', floor, [(front_y, top_z), (mid_y, mid_z)])):
            name = f'STF-{st}-{suffix}'
            measure = flight_measure(model, products[name], host, [products[n] for n in voids[host.args[2]]])
            area = measure['width_m']*(mid_y-front_y)
            # Guard the intended support interfaces against the IFC stair properties.
            e = products[name]
            if abs((e.args[8]-1)*e.args[11]-(mid_y-front_y)) > 1e-7:
                raise ValueError('Source stair run differs from proposed support span')
            apply(name, measure, stations, area,
                  [measure['centroid_m'][0], (front_y+mid_y)/2, (stations[0][1]+stations[1][1])/2])
        centre = ((lg['min']+lg['max'])/2).tolist()
        measure = {'gross_volume_m3': float(lg['volume']), 'owned_volume_m3': float(lg['volume']),
                   'upper_bearing_overlap_m3': 0., 'centroid_m': centre}
        area = float(np.prod((lg['max']-lg['min'])[:2]))
        apply(landing.args[2], measure, [(centre[1], mid_z)], area, [*centre[:2], mid_z])
    method='H03_SOURCE_DERIVED_RELEASED_GRAVITY_STRIPS' if 'A01_H03_Stair' in model.psets(products['STF-1F-A']) else 'H02_RELEASED_GRAVITY_STRIPS'
    if owned_wall_cells:method='H03_C_RELEASED_GRAVITY_STRIPS_ON_OWNED_WALL_CELLS'
    return {'method': method, 'sources': records,
            'mass_scope': 'Total mass and x/y first moments retained; vertical centroid and rotary inertia approximate',
            'stiffness_and_anchorage_design': 'NOT_CHECKED'}
