"""Independent IFC geometry/schema audit; no engineering approval is inferred."""
import argparse
from pathlib import Path
import numpy as np
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.validate
from structural_ai.ifc_reader import Model
from structural_ai.provenance import file_hash, write_json


def audit(path):
    f = ifcopenshell.open(path)
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    subset = Model(path)
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    # Compare gross extrusions first; separately inspect subtraction of voids.
    settings.set('disable-opening-subtractions', True)
    rows = []
    for kind in ('IfcColumn','IfcBeam','IfcWall','IfcSlab','IfcStairFlight','IfcOpeningElement'):
        for product in f.by_type(kind):
            row = {'id': product.id(), 'guid': product.GlobalId, 'name': product.Name, 'kind': kind}
            try:
                shape = ifcopenshell.geom.create_shape(settings, product)
                vertices = np.array(shape.geometry.verts).reshape(-1,3)
                faces = np.array(shape.geometry.faces).reshape(-1,3)
                triangles = vertices[faces]
                volume = abs(float(np.sum(np.einsum('ij,ij->i', triangles[:,0],
                    np.cross(triangles[:,1],triangles[:,2])))/6))
                expected = subset.solid_geometry(subset[product.id()])
                row.update({'min_m':vertices.min(0).tolist(),'max_m':vertices.max(0).tolist(),
                    'gross_volume_m3':volume,'subset_volume_m3':expected['volume'],
                    'bbox_match':bool(np.allclose(vertices.min(0),expected['min'],atol=1e-7) and
                                      np.allclose(vertices.max(0),expected['max'],atol=1e-7)),
                    'volume_match':bool(np.isclose(volume,expected['volume'],rtol=1e-7,atol=1e-8))})
            except Exception as exc:
                row['geometry_error'] = type(exc).__name__+': '+str(exc)
            rows.append(row)
    voids = []
    settings.set('disable-opening-subtractions', False)
    for rel in f.by_type('IfcRelVoidsElement'):
        host = rel.RelatingBuildingElement
        shape = ifcopenshell.geom.create_shape(settings, host)
        v = np.array(shape.geometry.verts).reshape(-1,3)
        tri = v[np.array(shape.geometry.faces).reshape(-1,3)]
        net = abs(float(np.sum(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])))/6))
        gross = next(r['gross_volume_m3'] for r in rows if r['id']==host.id())
        voids.append({'host_guid':host.GlobalId,'opening_guid':rel.RelatedOpeningElement.GlobalId,
                      'host_name':host.Name,'gross_m3':gross,'net_m3':net,'void_removes_volume':net<gross-1e-8})
    return {'file':Path(path).name,'sha256':file_hash(Path(path)),'schema':f.schema,
            'schema_findings':[{'level':s.get('level'),'message':s['message'],
                                'instance':str(s.get('instance',''))} for s in log.statements],
            'products':rows,'voids':voids,'engineering_approval':False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ifc',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    result = audit(a.ifc)
    write_json(a.output,result)
    print({'products':len(result['products']),'schema_findings':len(result['schema_findings']),
           'geometry_mismatches':sum(not r.get('bbox_match') or not r.get('volume_match') for r in result['products']),
           'voids_without_subtraction':sum(not v['void_removes_volume'] for v in result['voids'])})
    # Schema findings are reported separately; geometry mismatches fail this audit.
    raise SystemExit(0 if all(r.get('bbox_match') and r.get('volume_match') for r in result['products'])
                     and all(v['void_removes_volume'] for v in result['voids']) else 1)
