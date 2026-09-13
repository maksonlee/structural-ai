"""Independent geometry formulations and the real IFC boundary used by review sheets."""
from pathlib import Path
import importlib.util
import unittest
import numpy as np
import yaml
from shapely.geometry import Polygon
from structural_ai.coordination import volume_centroid, overhead_height, projected_beams, read_geometry, screens
from structural_ai.cli import load_project, received_scheme

ROOT=Path(__file__).resolve().parents[1]


class CoordinationGeometryTests(unittest.TestCase):
    def test_beam_plan_uses_elevation_instead_of_storey_name(self):
        objects={'a':{'name':'first-span','kind':'IFCBEAM','max':[5,1,4]},
                 'b':{'name':'upper-span','kind':'IFCBEAM','max':[5,1,7.6]}}
        levels={'ground':0.,'upper':4.,'roof':7.6}
        self.assertEqual([o['name'] for o in projected_beams(objects,levels,'ground')],['first-span'])
        self.assertEqual([o['name'] for o in projected_beams(objects,levels,'upper')],['upper-span'])
        self.assertEqual([o['name'] for o in projected_beams(objects,levels,'roof')],['upper-span'])

    def test_asymmetric_tetrahedron_volume_and_centroid(self):
        # Axis intercepts 1, 2, 3: V=abc/6=1; centroid=(a,b,c)/4.
        shift=np.array([13.,-7.,9.])
        vertices=np.array([[0,0,0],[1,0,0],[0,2,0],[0,0,3]])+shift
        faces=np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
        for winding in (faces,faces[:,::-1]):
            volume,centre=volume_centroid(vertices,winding)
            self.assertAlmostEqual(volume,1.)
            np.testing.assert_allclose(centre,shift+[.25,.5,.75],atol=1e-10)

    def test_vertical_ray_nearest_plane_and_missing_overhead(self):
        # Triangle is on z=2+x/2-y/4. At (.5,.5), z=2.125.
        face=np.array([[0,0,2],[2,0,3],[0,2,1.5]])
        triangles=np.array([face,face+[0,0,4]])
        self.assertAlmostEqual(overhead_height(triangles,.5,.5,1.),2.125)
        self.assertAlmostEqual(overhead_height(triangles,.5,.5,3.),6.125)
        self.assertIsNone(overhead_height(triangles,3.,3.,0.))
        self.assertIsNone(overhead_height(triangles,.5,.5,8.))


@unittest.skipUnless(importlib.util.find_spec('ifcopenshell'), 'Requires real optional IfcOpenShell backend')
class CoordinationIFCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory,project,_,_,_=load_project(ROOT/'project')
        cls.data=read_geometry(received_scheme(directory,project))
        cls.config=yaml.safe_load((ROOT/'project/structural/inputs/coordination.yaml').read_text())
        cls.review=screens(*cls.data,cls.config)

    def test_stair_centroids_against_independent_extrusion_integral(self):
        _,objects,geometry,_,_,_=self.data
        for name,g in geometry.items():
            if objects[name]['kind']!='IFCSTAIRFLIGHT':continue
            centroid=Polygon(g['profile']).centroid
            # The source stairs extrude normal to their profile plane.
            depth=g['solid'].args[3]
            expected=(g['matrix']@np.array([centroid.x,centroid.y,depth/2,1]))[:3]
            np.testing.assert_allclose(objects[name]['centroid_m'],expected,atol=1e-8)

    def test_voids_are_subtracted_and_do_not_become_occupied_room_area(self):
        _,objects,_,_,holes,_=self.data
        self.assertEqual(sum(map(len,holes.values())),13)
        for host in holes:self.assertLess(objects[host]['net_m3'],objects[host]['gross_m3'])
        for floor in self.review['floors']:
            self.assertIsNone(floor['occupied_room_area_m2'])
            self.assertLess(floor['net_slab_projection_m2'],floor['gross_projection_m2'])

    def test_unknown_finishes_and_roof_remain_open(self):
        self.assertEqual(len(self.review['stairs']),6)
        self.assertEqual(len(self.review['dimension_checks']),18)
        self.assertEqual(self.review['whole_route_code_status'],'NOT_CHECKED')
        for row in self.review['stairs']:
            self.assertAlmostEqual(row['width_scenarios'][0]['margin_to_project_target_m'],0.)
            self.assertEqual(row['width_scenarios'][1]['status'],'BELOW_PROJECT_TARGET')
        roof=[r for r in self.review['stair_headroom'] if r['name'].startswith('STF-3F-')]
        self.assertTrue(all(r['missing_overhead_samples']>0 for r in roof))


if __name__=='__main__':unittest.main()
