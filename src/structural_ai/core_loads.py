"""Synthetic H03 equipment and lightweight-panel gravity, not support design."""
from collections import defaultdict
import numpy as np
from shapely.geometry import box
from .rectilinear import area_weights
from .core_revision import horizontal_polygon


def apply_core_loads(model, products, geometry, voids, floor_cells, panels,
                     basis, gravity, ledger, grav):
    records = []

    def distribute(label, source, region, weight, case, mass=False):
        if not np.isfinite(weight) or weight <= 0:
            raise ValueError('Equipment/panel weight must be positive and finite')
        values = defaultdict(float)
        covered = 0.
        for cell, nodes in floor_cells[source]:
            part = cell.intersection(region)
            if part.area <= 1e-12:
                continue
            weights = area_weights(part, cell.bounds) / region.area
            covered += part.area
            gravity(case, nodes, weight * sum(weights), mass, weights / sum(weights))
            for n, w in zip(nodes, weights):
                values[n] += weight * w
        if abs(covered - region.area) > 1e-7:
            raise ValueError(f'{label} is not fully supported by the receiving slab mesh')
        record = {'label': label, 'support_source_name': source,
                  'support_source_guid': products[source].args[0],
                  'case': case, 'weight_kN': weight, 'added_modal_mass': mass,
                  'patch_centroid_xy_m': [region.centroid.x, region.centroid.y],
                  'receiving_nodes': [{'node': n, 'downward_kN': w} for n, w in sorted(values.items())]}
        records.append(record)
        return record

    for name, props in panels.items():
        g = geometry[name]
        footprint = horizontal_polygon(g)
        parts = [(footprint, g['max'][2]-g['min'][2])]
        for hole in voids[name]:
            h = geometry[hole]
            hole_plan = horizontal_polygon(h)
            height = max(0., min(g['max'][2], h['max'][2])-max(g['min'][2], h['min'][2]))
            split = []
            for region, density in parts:
                outside, inside = region.difference(hole_plan), region.intersection(hole_plan)
                if outside.area > 1e-12: split.append((outside, density))
                if inside.area > 1e-12 and density-height > 1e-12: split.append((inside, density-height))
            parts = split
        volume = sum(region.area*height for region,height in parts)
        thickness = min((g['max']-g['min'])[:2])
        weight = volume / thickness * props['FaceWeight_kN_m2']
        if abs(g['min'][2]) < 1e-8:
            records.append({'label': name, 'source_guid': products[name].args[0],
                            'weight_kN': float(weight), 'case': 'GROUND_SUPPORTED_PENDING_FOUNDATION',
                            'added_modal_mass': False, 'receiving_nodes': []})
        else:
            floor = 'S-' + name.rsplit('-', 1)[1]
            for region, height in parts:
                r = distribute(name, floor, region, region.area*height/thickness*props['FaceWeight_kN_m2'], 'D_PANEL', True)
                r['source_guid'] = products[name].args[0]
        ledger.append({'source': name, 'self_weight_kN': float(weight),
                       'note': 'Synthetic lightweight panel, no RC stiffness; 1F panels go to ground/future foundation; upper panels to supporting floor.'})

    lift = basis['lift']; roof = basis['roof']
    scale = float(lift.get('adopted_mass_multiplier', 1.0))
    car = lift['assumed_car_and_sling_kg']
    payload = lift['rated_payload_kg']
    permanent = (2*car + payload*lift['assumed_counterweight_balance_fraction'] +
                 lift['assumed_machine_rails_ropes_and_miscellaneous_kg']) * grav/1000 * scale
    live = payload * grav/1000
    region = box(geometry['SW-SHARED-STAIR-LIFT-1F']['max'][0],
                 geometry['SW-LIFT-S-1F']['max'][1],
                 geometry['SW-LIFT-E-1F']['min'][0],
                 geometry['SW-LIFT-N-1F']['min'][1])
    distribute('lift_permanent', 'S-LIFT-CAP', region, permanent, 'D_EQUIPMENT', True)
    distribute('lift_payload', 'S-LIFT-CAP', region, live, 'L_LIFT')
    envelope = (permanent + live) * lift['vertical_envelope_factor']
    distribute('lift_head_envelope', 'S-LIFT-CAP', region, envelope, 'LIFT_HEAD_ENVELOPE')
    distribute('lift_buffer_alternative', 'S-PIT', region, envelope, 'LIFT_BUFFER_ENVELOPE')
    roof_weight = float(roof.get('adopted_equipment_dead_kN', roof['synthetic_equipment_dead_kN']))
    distribute('roof_equipment', 'S-RF', box(*roof['proposed_patch_bounds_m']), roof_weight, 'D_EQUIPMENT', True)
    return {'status': 'SYNTHETIC_GLOBAL_LOAD_SURROGATES_NOT_VENDOR_SUPPORT_DESIGN',
            'records': records, 'lift_permanent_kN': permanent, 'lift_payload_kN': live,
            'lift_vertical_envelope_kN': envelope, 'roof_permanent_kN': roof_weight,
            'ground_panel_weight_kN': sum(r['weight_kN'] for r in records if r['case'].startswith('GROUND')),
            'limits': ['Head and buffer entire-system envelopes are alternative cases.',
                       'Impact is excluded from modal mass; no physical buffer dynamics.',
                       'Equipment patch and panel footprint surrogates retain global first moments, not local bracket/lintel reactions.',
                       'Tanks, detailed MEP, anchorage and soil remain unresolved.']}
