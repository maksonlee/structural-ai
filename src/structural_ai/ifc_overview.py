"""Render the case's actual IFC mesh as an annotated orthographic SVG."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import yaml

from .provenance import file_hash, write_json


def draw(project: Path, output: Path):
    project = project.resolve()
    root = project.parent
    config = yaml.safe_load((project / 'project.yaml').read_text())
    source = project / config['architectural_handoff']['core_candidate_ifc']
    digest = file_hash(source)
    if digest != config['architectural_handoff']['core_candidate_sha256']:
        raise ValueError('Review the changed architectural candidate before rendering')
    if digest != file_hash(project / config['authority']['physical_geometry']):
        raise ValueError('Architectural and adopted structural geometry differ')
    if output.exists():
        raise ValueError('Use an unused output directory')
    model = ifcopenshell.open(str(source))
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    settings.set('disable-opening-subtractions', False)
    shapes = {}
    for kind in ('IfcColumn', 'IfcBeam', 'IfcWall', 'IfcSlab', 'IfcStairFlight'):
        for product in model.by_type(kind):
            shape = ifcopenshell.geom.create_shape(settings, product)
            vertices = np.array(shape.geometry.verts).reshape(-1, 3)
            faces = np.array(shape.geometry.faces).reshape(-1, 3)
            if not len(faces) or not np.isfinite(vertices).all():
                raise ValueError('Invalid mesh: ' + product.Name)
            shapes[product.Name] = dict(name=product.Name, guid=product.GlobalId,
                                        kind=kind, vertices=vertices, faces=faces)
    counts = Counter(row['kind'].upper() for row in shapes.values())
    expected = {kind: count for kind, count in config['compatibility']['physical_counts'].items()
                if kind != 'IFCOPENINGELEMENT'}
    if counts != expected:
        raise ValueError('Physical product coverage differs from the reviewed source')
    # Actual void relations are consumed by IfcOpenShell; opening solids are not drawn.
    voids = []
    for rel in model.by_type('IfcRelVoidsElement'):
        row = shapes[rel.RelatingBuildingElement.Name]
        triangles = row['vertices'][row['faces']]
        net = abs(float(np.einsum('ij,ij->i', triangles[:, 0],
                        np.cross(triangles[:, 1], triangles[:, 2])).sum() / 6))
        gross_settings = ifcopenshell.geom.settings()
        gross_settings.set('use-world-coords', True)
        gross_settings.set('disable-opening-subtractions', True)
        gross_shape = ifcopenshell.geom.create_shape(gross_settings, rel.RelatingBuildingElement)
        verts = np.array(gross_shape.geometry.verts).reshape(-1, 3)
        tri = verts[np.array(gross_shape.geometry.faces).reshape(-1, 3)]
        gross = abs(float(np.einsum('ij,ij->i', tri[:, 0],
                          np.cross(tri[:, 1], tri[:, 2])).sum() / 6))
        if not 0 < net < gross - 1e-8:
            raise ValueError('Opening did not remove volume: ' + rel.RelatedOpeningElement.Name)
        voids.append(dict(host_guid=row['guid'], opening_guid=rel.RelatedOpeningElement.GlobalId,
                          gross_volume_m3=gross, net_volume_m3=net))

    azimuth, elevation = np.deg2rad([-125, 26])
    camera = np.array([np.cos(elevation)*np.cos(azimuth),
                       np.cos(elevation)*np.sin(azimuth), np.sin(elevation)])
    right = np.array([-np.sin(azimuth), np.cos(azimuth), 0])
    up = np.cross(camera, right)
    basis = np.array([right, -up, camera]).T
    points = np.vstack([row['vertices'] for row in shapes.values()])
    projected = points @ basis
    lo, hi = projected[:, :2].min(0), projected[:, :2].max(0)
    scale = min(1130/(hi[0]-lo[0]), 820/(hi[1]-lo[1]))
    origin = np.array([70, 200]) - lo*scale

    def project_point(xyz):
        return (np.asarray(xyz) @ basis)[:2]*scale + origin

    def style(row):
        name, kind = row['name'], row['kind']
        if kind == 'IfcStairFlight' or name.startswith('STL-'):
            return '#d98927', 1.0
        if name.startswith('SW-SHARED-'):
            return '#168c82', .9
        if name.startswith('SW-LIFT-'):
            return '#4b8fbe', .16
        if kind == 'IfcWall':
            return '#91a7b4', .08
        if kind == 'IfcSlab':
            return '#9eafbc', .10
        return '#a3b1bd', 1.0

    def shade(color, normal):
        normal = normal / np.linalg.norm(normal)
        light = np.array([-.3, -.5, .81])
        factor = .68 + .32*abs(float(normal @ light))
        rgb = [round(int(color[i:i+2], 16)*factor) for i in (1, 3, 5)]
        return '#' + ''.join(f'{value:02x}' for value in rgb)

    polygons = []
    for row in shapes.values():
        color, opacity = style(row)
        vertices = row['vertices']
        uv = (vertices @ basis)[:, :2]*scale + origin
        for face in row['faces']:
            triangle = vertices[face]
            normal = np.cross(triangle[1]-triangle[0], triangle[2]-triangle[0])
            if np.linalg.norm(normal) < 1e-12:
                continue
            coordinates = ' '.join(f'{x:.2f},{y:.2f}' for x, y in uv[face])
            fill = shade(color, normal)
            markup = (f'<polygon points="{coordinates}" fill="{fill}" fill-opacity="{opacity}" '
                      f'data-guid="{row["guid"]}"/>')
            polygons.append((float(triangle.mean(0) @ camera), markup))

    def centre(name):
        verts = shapes[name]['vertices']
        return (verts.min(0)+verts.max(0))/2

    labels = [
        ('Elevator shaft', 'Blue: enclosing shaft walls', '#397dab', centre('SW-LIFT-N-3F'), 'SW-LIFT-N-3F'),
        ('Shared core wall', 'Teal: stair / elevator interface', '#137d73', centre('SW-SHARED-STAIR-LIFT-2F'), 'SW-SHARED-STAIR-LIFT-2F'),
        ('Stairs + landings', 'Amber: actual stair geometry', '#b26b16', centre('STF-2F-A'), 'STF-2F-A'),
    ]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1200" viewBox="0 0 1800 1200">',
           '<title>Architectural proposal: actual IFC model</title>',
           '<desc>Three-storey RC frame with stairs, elevator shaft and shared wall. Floors and enclosing walls are transparent for visibility. Simulated review model.</desc>',
           f'<metadata>{html.escape(json.dumps({"source_sha256": digest, "opening_subtractions": True}))}</metadata>',
           '<rect width="1800" height="1200" fill="#f8fafc"/>',
           '<g font-family="Arial, sans-serif" fill="#233647">',
           '<text x="65" y="74" font-size="42" font-weight="700">Architectural proposal · IFC model</text>',
           '<text x="65" y="119" font-size="25" fill="#596b79">Three-storey RC office · approximately 18 × 12 m · Taipei</text>',
           '<path d="M65 152H1735" stroke="#dce4ea" stroke-width="2"/>',
           *[markup for _, markup in sorted(polygons, key=lambda item: item[0])]]
    label_records = []
    for index, (title, subtitle, color, target, name) in enumerate(labels):
        y = 400 + index*180
        x, py = project_point(target)
        svg.extend([
            f'<path d="M{x:.2f} {py:.2f}L1240 {y-10}H1290" fill="none" stroke="{color}" stroke-width="2.5"/>',
            f'<circle cx="{x:.2f}" cy="{py:.2f}" r="7" fill="{color}" stroke="white" stroke-width="2"/>',
            f'<text x="1305" y="{y}" font-size="30" font-weight="700" fill="{color}">{title}</text>',
            f'<text x="1305" y="{y+40}" font-size="23" fill="#596b79">{subtitle}</text>'])
        label_records.append(dict(label=title, target_guid=shapes[name]['guid'],
                                  target_xyz_m=target.tolist()))
    svg.extend([
        '<path d="M65 1070H1735" stroke="#dce4ea" stroke-width="2"/>',
        '<text x="65" y="1115" font-size="24">Floors and enclosing walls are transparent to reveal the core. Colours identify parts.</text>',
        '<text x="65" y="1155" font-size="23" fill="#596b79">Rendered from core-candidate.ifc · Simulated proposal · Design review remains open</text>',
        '</g></svg>'])
    output.mkdir(parents=True)
    path = output / 'ifc-overview.svg'
    path.write_text('\n'.join(svg), encoding='utf-8')
    record = dict(source=source.relative_to(root).as_posix(), source_sha256=digest,
                  ifcopenshell_version=ifcopenshell.version, renderer='IFC triangles, orthographic SVG projection',
                  camera_azimuth_degrees=-125, camera_elevation_degrees=26,
                  products=[dict(name=row['name'], guid=row['guid'], kind=row['kind'],
                                 vertices=len(row['vertices']), triangles=len(row['faces'])) for row in shapes.values()],
                  voids=voids, labels=label_records, omitted_physical_products=[],
                  colour_and_transparency='Presentation only; source geometry unchanged',
                  output_sha256=file_hash(path), engineering_approval=False)
    write_json(output / 'ifc-overview.json', record)
    print(json.dumps(dict(products=len(shapes), checked_voids=len(voids), svg_sha256=file_hash(path))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path('project'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    draw(args.project, args.output)
