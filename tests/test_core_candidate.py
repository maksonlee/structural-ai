"""Known geometry/load integrals and the actual architect-to-converter boundary."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import math
import unittest
import contextlib
import io
import json
import numpy as np
import yaml
from shapely.geometry import Polygon, box
from structural_ai.rectilinear import area_weights
from structural_ai.core_revision import revise_core, horizontal_polygon
from structural_ai.ifc_reader import Model
from structural_ai.stair_transfer import flight_measure
from structural_ai.core_review import portal_clearance
from structural_ai.cli import load_project, received_scheme

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'project'


class IntegrationTests(unittest.TestCase):
    def test_clipped_l_area_first_and_mixed_moments(self):
        region=box(0,0,2,2).difference(box(1,1,2,2))
        weights=area_weights(region,(0,0,2,2))
        # Full-square integrals (1 each) minus upper-right quadrant integrals.
        np.testing.assert_allclose(weights,[15/16,13/16,7/16,13/16],atol=1e-12)
        self.assertAlmostEqual(sum(weights),3)
        self.assertAlmostEqual(np.dot(weights,[0,2,2,0]),2.5)
        self.assertAlmostEqual(np.dot(weights,[0,0,2,2]),2.5)
        self.assertAlmostEqual(np.dot(weights,[0,0,4,0]),1.75)

    def test_outside_and_nonorthogonal_regions_are_rejected(self):
        with self.assertRaises(ValueError):area_weights(box(-1,0,2,2),(0,0,2,2))
        with self.assertRaisesRegex(ValueError,'Non-orthogonal'):
            area_weights(Polygon([(0,0),(2,0),(0,2)]),(0,0,2,2))

    def test_portal_column_intrusion_is_not_a_door_swing_pass(self):
        objects={'SW-STAIR-W-1F':{'kind':'IFCWALL','min':[6.12,3.5,0],'max':[6.37,11.68,4]},
                 'B2':{'kind':'IFCCOLUMN','guid':'known-column','min':[6,4.2,0],'max':[6.6,4.8,4]}}
        p={'vestibule':{'side_portal_y_m':[4.6,5.9]}}
        result=portal_clearance(p,objects,.01)
        self.assertAlmostEqual(result['finished_unobstructed_width_m'],1.08)
        self.assertEqual(result['column_conflicts'][0]['source_guid'],'known-column')


class CandidateBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal=yaml.safe_load((PROJECT/'architect/outputs/core-proposal.yaml').read_text())
        cls.scheme=yaml.safe_load((PROJECT/'architect/outputs/scheme.yaml').read_text())
        cls.path=PROJECT/'architect/outputs/core-candidate.ifc'
        cls.model=Model(cls.path)

    def test_candidate_reproduces_without_altering_adopted_source(self):
        directory,project,active,_,_=load_project(PROJECT)
        source=received_scheme(directory,project)
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,active)}
        with TemporaryDirectory() as directory:
            out=Path(directory)/'candidate.ifc'
            receipt=revise_core(source,self.proposal,out,self.scheme)
            self.assertEqual(out.read_bytes(),self.path.read_bytes())
            self.assertTrue(receipt['main_frame_unchanged'])
            self.assertFalse(receipt['adopted'])
        self.assertEqual({p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,active)},before)

    def test_six_flight_volumes_and_bearing_deduction(self):
        m=self.model;products={e.args[2]:e for e in m.entities.values() if e.type in ('IFCSTAIRFLIGHT','IFCSLAB','IFCOPENINGELEMENT')}
        voids={}
        for r in m.by_type('IFCRELVOIDSELEMENT'):voids.setdefault(m[r.args[4]].args[2],[]).append(m[r.args[5]])
        for e in m.by_type('IFCSTAIRFLIGHT'):
            st,letter=e.args[2].split('-')[1:]
            host=products['STL-'+st+'-MID'] if letter=='A' else products['S-'+{'1F':'2F','2F':'3F','3F':'RF'}[st]]
            n,_,r,t=e.args[8:12];width=1.33;bearing=.15
            vertical_waist=.18*math.sqrt(1+(r/t)**2)
            expected=width*((n-1)*t*(vertical_waist+r/2)+bearing*(vertical_waist+r))
            measure=flight_measure(m,e,host,voids.get(host.args[2],[]))
            self.assertAlmostEqual(measure['gross_volume_m3'],expected,places=9)
            self.assertAlmostEqual(measure['upper_bearing_overlap_m3'],width*bearing*.18,places=9)
            self.assertAlmostEqual(measure['owned_volume_m3'],expected-width*bearing*.18,places=9)

    def test_l_landing_is_not_bounding_rectangle(self):
        e=next(e for e in self.model.by_type('IFCSLAB') if e.args[2]=='STL-1F-MID')
        p=horizontal_polygon(self.model.solid_geometry(e))
        self.assertAlmostEqual(p.area,2.88*1.47+1.55*.29,places=9)
        self.assertLess(p.area,box(*p.bounds).area)


class CandidateLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from structural_ai.model_builder import create
        cls.temp=TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        path=Path(cls.temp.name)
        historical=ROOT/'tests/fixtures/h02-analysis.yaml'
        cfg=yaml.safe_load((historical if historical.exists() else PROJECT/'structural/inputs/analysis.yaml').read_text())
        cfg['revision']='H03-B';cfg['base']['elevation_m']=-1.8
        config=path/'candidate-analysis.yaml';config.write_text(yaml.safe_dump(cfg))
        with contextlib.redirect_stdout(io.StringIO()):
            cls.model=create(PROJECT/'architect/outputs/core-candidate.ifc',config,path,
                architect_scheme=PROJECT/'architect/outputs/scheme.yaml',
                equipment_basis=PROJECT/'structural/design/core-interface-loads.yaml')
        cls.loads=json.loads((path/'core_loads.json').read_text())

    def test_mass_excludes_impact_payload_and_ground_panels(self):
        m=self.model
        weight=-sum(ld['vector'][2] for case in ('D_SELF','D_SUPER','L_PARTITION','D_PANEL','D_EQUIPMENT')
                    for ld in m['load_cases'][case]['nodal_loads'])
        mass=sum(n['mass'][0] for n in m['nodal_masses'])
        self.assertAlmostEqual(mass*m['materials']['g_m_s2'],weight,places=7)
        self.assertGreater(self.loads['ground_panel_weight_kN'],0)
        for r in self.loads['records']:
            if 'ENVELOPE' in r['case'] or r['case']=='L_LIFT':self.assertFalse(r['added_modal_mass'])
            if r['case'].startswith('GROUND'):self.assertEqual(r['receiving_nodes'],[])
        self.assertFalse(any(e['source_name'].startswith('NW-VEST') for e in m['elements']))

    def test_equipment_position_and_alternative_envelopes(self):
        m=self.model;xyz={n['id']:np.array(n['xyz']) for n in m['nodes']}
        for r in self.loads['records']:
            if not r['receiving_nodes']:continue
            actual=sum((n['downward_kN']*xyz[n['node']][:2] for n in r['receiving_nodes']),start=np.zeros(2))
            np.testing.assert_allclose(actual,r['weight_kN']*np.array(r['patch_centroid_xy_m']),atol=1e-8)
        total=lambda case:-sum(n['vector'][2] for n in m['load_cases'][case]['nodal_loads'])
        loaded=(2915+700)*9.80665/1000
        self.assertAlmostEqual(self.loads['lift_vertical_envelope_kN'],2*loaded,places=8)
        for case in ('SERVICE_LIFT_HEAD','SERVICE_LIFT_BUFFER'):
            self.assertAlmostEqual(total(case)-total('SERVICE_ILLUSTRATION'),loaded,places=7)


if __name__=='__main__':unittest.main()
