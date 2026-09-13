"""Physical ownership and whole-candidate boundaries, independent of solver output."""
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
import yaml
from structural_ai.model_builder import create
from structural_ai.wall_interfaces import intervals
from structural_ai.joint_constraints import validate_constraints
from structural_ai.opensees_runner import resultant

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'project'


class WallOwnershipTests(unittest.TestCase):
    def test_overlapping_interval_owners_are_subtracted_once(self):
        self.assertEqual(intervals(0.,1.,[(.2,.6),(.4,.8)]),[(0.,.2),(.8,1.)])
        np.testing.assert_allclose(intervals(6.12,6.37,[(5.7,6.3)]),[[6.3,6.37]])
        self.assertEqual(intervals(0.,1.,[(-1.,2.)]),[])


class WholeCandidateInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.path=Path(cls.temp.name)
        cfg=yaml.safe_load((PROJECT/'structural/inputs/analysis.yaml').read_text())
        cfg['revision']='H03-C';cfg['base']['elevation_m']=-1.8
        config=cls.path/'analysis.yaml';config.write_text(yaml.safe_dump(cfg))
        with contextlib.redirect_stdout(io.StringIO()):
            cls.model=create(PROJECT/'architect/outputs/core-candidate.ifc',config,cls.path,
                architect_scheme=PROJECT/'architect/outputs/scheme.yaml',
                equipment_basis=PROJECT/'structural/design/core-interface-loads.yaml')
        cls.xyz={n['id']:np.array(n['xyz']) for n in cls.model['nodes']}

    def test_independent_horizontal_slice_ownership_and_direct_groups(self):
        from scripts.audit_wall_interfaces import audit
        record=audit(self.path/'analytical_model.json')
        self.assertTrue(record['passed'])
        # Column intersections: (.18*.60 + .18*.28)*(11.2+1.8).
        self.assertAlmostEqual(record['intersection_volume_by_owner_m3']['IFCCOLUMN'],
                               (.18*.60+.18*.28)*13,places=8)
        # Seven source-plan intersections per floor, times 0.52 m web depth.
        plan_area=(.07*.40+.07*.18+.08*.40+.08*6.90+2.88*.18+.25*.40+.25*.18)
        self.assertAlmostEqual(record['intersection_volume_by_owner_m3']['IFCBEAM'],3*.52*plan_area,places=8)
        self.assertEqual(len(record['frame_contacts']),31)
        self.assertEqual(record['contacts_without_direct_kinematic_group'],0)

    def test_joint_forest_limits_and_source_derived_web_centroid(self):
        m=self.model
        self.assertTrue(validate_constraints(m,self.xyz))
        master={link['slave']:link['master'] for link in m['rigid_joints']}
        self.assertFalse(set(master)&set(master.values()))
        for element in m['elements']:
            if element['role']=='beam':
                np.testing.assert_allclose(element['offset'],[0.,0.,-(.70+.18)/2],atol=1e-14)
            if element['role']=='wall':
                self.assertGreater(m['sections'][element['section']]['t'],0.)
        audit=json.loads((self.path/'joint_interfaces.json').read_text())
        self.assertTrue(all(max(group['extent_m'])<.9 for group in audit['groups']))

    def test_mass_and_stair_resultants_survive_interface_partition(self):
        m=self.model
        weight=-sum(ld['vector'][2] for key in ('D_SELF','D_SUPER','L_PARTITION','D_PANEL','D_EQUIPMENT')
                    for ld in m['load_cases'][key]['nodal_loads'])
        self.assertAlmostEqual(sum(n['mass'][0] for n in m['nodal_masses'])*9.80665,weight,places=7)
        stairs=json.loads((self.path/'stair_transfer.json').read_text())
        self.assertEqual(stairs['method'],'H03_C_RELEASED_GRAVITY_STRIPS_ON_OWNED_WALL_CELLS')
        for source in stairs['sources']:
            for component in source['components']:
                self.assertLess(component['Fz_Mx_My_residual_max_kN_kNm'],1e-7)

    def test_calibration_resultants_follow_source_floor_area(self):
        from structural_ai.ifc_reader import Model
        from structural_ai.core_revision import horizontal_polygon
        physical=Model(PROJECT/'architect/outputs/core-candidate.ifc')
        slabs={e.args[2]:e for e in physical.by_type('IFCSLAB')}
        for axis,key in ((0,'X100_CALIBRATION'),(1,'Y100_CALIBRATION')):
            expected=np.zeros(6)
            for name,z in (('S-2F',4.),('S-3F',7.6),('S-RF',11.2)):
                slab=slabs[name];region=horizontal_polygon(physical.solid_geometry(slab))
                for relation in physical.by_type('IFCRELVOIDSELEMENT'):
                    if relation.args[4].id==slab.id:
                        region=region.difference(horizontal_polygon(physical.solid_geometry(physical[relation.args[5]])))
                force=np.zeros(3);force[axis]=100*(z+1.8)/(4+7.6+11.2+3*1.8)
                expected+=np.r_[force,np.cross([region.centroid.x,region.centroid.y,z],force)]
            actual=resultant(self.xyz,[(ld['node'],ld['vector']) for ld in self.model['load_cases'][key]['nodal_loads']])
            np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-7)

    def test_load_moments_use_actual_node_coordinates(self):
        from shapely.geometry import box
        from shapely.ops import unary_union
        from structural_ai.ifc_reader import Model
        from structural_ai.core_revision import horizontal_polygon
        source=Model(PROJECT/'architect/outputs/core-candidate.ifc')
        expected=np.zeros(6)
        for name,z in (('S-2F',4.),('S-3F',7.6)):
            slab=next(e for e in source.by_type('IFCSLAB') if e.args[2]==name)
            net=horizontal_polygon(source.solid_geometry(slab))
            for relation in source.by_type('IFCRELVOIDSELEMENT'):
                if relation.args[4].id==slab.id:
                    net=net.difference(horizontal_polygon(source.solid_geometry(source[relation.args[5]])))
            occupied=[]
            for kind in ('IFCCOLUMN','IFCWALL'):
                for element in source.by_type(kind):
                    g=source.solid_geometry(element)
                    if g['min'][2]<z-1e-6 and g['max'][2]>=z-1e-6:
                        occupied.append(box(*g['min'][:2],*g['max'][:2]))
            net=net.difference(unary_union(occupied));force=np.array([0.,0.,-net.area*2.941995])
            expected+=np.r_[force,np.cross([net.centroid.x,net.centroid.y,z],force)]
        for case,target in (('L_OFFICE',expected),
                            ('L_POINT_SINGLE',np.r_[[0.,0.,-9.80665],np.cross([3.,7.8,4.],[0.,0.,-9.80665])])):
            actual=resultant(self.xyz,[(ld['node'],ld['vector']) for ld in self.model['load_cases'][case]['nodal_loads']])
            np.testing.assert_allclose(actual,target,rtol=0,atol=1e-7)

    def test_all_load_resultants_are_mesh_independent(self):
        with contextlib.redirect_stdout(io.StringIO()):
            finer=create(PROJECT/'architect/outputs/core-candidate.ifc',self.path/'analysis.yaml',
                         self.path/'mesh050',mesh_size=.5,
                         architect_scheme=PROJECT/'architect/outputs/scheme.yaml',
                         equipment_basis=PROJECT/'structural/design/core-interface-loads.yaml')
        xyz={n['id']:np.array(n['xyz']) for n in finer['nodes']}
        for key,case in self.model['load_cases'].items():
            original=resultant(self.xyz,[(ld['node'],ld['vector']) for ld in case['nodal_loads']])
            refined=resultant(xyz,[(ld['node'],ld['vector']) for ld in finer['load_cases'][key]['nodal_loads']])
            np.testing.assert_allclose(original,refined,rtol=0,atol=1e-7,err_msg=key)

    def test_reviewed_h03c_numerical_inputs_include_joint_constraints(self):
        import hashlib
        fixture=json.loads((ROOT/'tests/fixtures/h03c_input_signature.json').read_text())
        self.assertIn('rigid_joints',fixture['signature_keys'])
        canonical=json.dumps({key:self.model[key] for key in fixture['signature_keys']},
                             sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),fixture['canonical_input_signature_sha256'])


if __name__=='__main__':unittest.main()
