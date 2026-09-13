"""Independent geometry and scope guards for the proposed architectural handoff."""
from copy import deepcopy
from pathlib import Path
import unittest

import numpy as np
import yaml

from structural_ai.coordination import read_geometry
from structural_ai.core_review import circle_gap, sector, flights, core_geometry, landing_polygon, evaluate
from structural_ai.cli import load_project, received_scheme

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'project'


class EnvelopeTests(unittest.TestCase):
    def test_exact_circle_bound_and_sector_area(self):
        # Independent 3-4-5 geometry: radii 1+2 leave a 2 m gap.
        self.assertAlmostEqual(circle_gap([0,0],1,[3,4],2),2)
        self.assertAlmostEqual(circle_gap([0,0],2,[3,0],2),-1)
        self.assertAlmostEqual(sector([0,0],2,0,90).area,np.pi,delta=.00005)
        with self.assertRaises(ValueError):circle_gap([0,0],-1,[3,0],2)

    def test_uniform_counts_and_landing_setback_known_coordinates(self):
        stair={'risers_by_storey':[[15,15],[14,13],[14,13]],'tread_m':.29,
               'first_up_nosing_y_m':5.90,'finish_vertical_build_up_m':.05}
        levels={'1F':0.,'2F':4.,'3F':7.6,'RF':11.2}
        rows=flights(stair,levels)
        np.testing.assert_allclose([r['riser_m'] for r in rows],[2/15]*3)
        np.testing.assert_allclose([r['a_start_y_m'] for r in rows],[5.90,5.90,6.19])
        np.testing.assert_allclose([r['a_end_y_m'] for r in rows],[9.96,9.67,9.96])
        np.testing.assert_allclose([r['b_end_y_m'] for r in rows],[5.61,5.90,6.19])
        for a,b in zip(rows,rows[1:]):
            self.assertAlmostEqual(b['a_start_y_m']-a['b_end_y_m'],.29)
        invalid=deepcopy(stair);invalid['risers_by_storey'][1]=[13,13]
        with self.assertRaisesRegex(ValueError,'uniform'):flights(invalid,levels)


class ProjectProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal=yaml.safe_load((PROJECT/'architect/outputs/core-proposal.yaml').read_text())
        cls.scheme=yaml.safe_load((PROJECT/'architect/outputs/scheme.yaml').read_text())
        cls.basis=yaml.safe_load((PROJECT/'structural/design/core-interface-loads.yaml').read_text())
        directory,project,_,_,_=load_project(PROJECT)
        _,cls.received,_,_,_,_=read_geometry(received_scheme(directory,project))
        _,cls.objects,_,_,_,cls.levels=read_geometry(PROJECT/'architect/outputs/core-candidate.ifc')
        cls.report=evaluate(cls.proposal,cls.basis,cls.scheme,cls.objects,cls.levels,9.80665,cls.received)

    def test_l_shaped_landing_area_has_explicit_step_setback(self):
        geometry=core_geometry(self.proposal,self.objects)
        p=landing_polygon(self.report['rows'][0],geometry)
        # 2.88 x 1.47 rear rectangle plus 1.55 x .29 side extension.
        self.assertAlmostEqual(p.area,2.88*1.47+1.55*.29,places=8)
        self.assertTrue(p.is_valid)

    def test_current_column_and_door_constraints(self):
        checks={x['id']:x for x in self.report['checks']}
        self.assertGreater(self.report['existing_central_door_example']['overlap_m2'],.1)
        self.assertGreater(checks['H03-C04']['value']['full_disc_separation_m'],.02)
        self.assertEqual(checks['H03-C05']['value']['door_bounding_box_column_intersection_m2'],0)
        self.assertEqual(checks['H03-C05']['status'],'PASS_PROPOSED_DIMENSIONS_ONLY')
        self.assertAlmostEqual(checks['H03-C05']['value']['actual_throat']['finished_unobstructed_width_m'],1.28)
        self.assertEqual(checks['H03-C05']['value']['actual_throat']['column_conflicts'],[])
        self.assertGreater(self.report['alternatives']['minimum_depth_shortfall_m'],.4)

    def test_equipment_envelopes_are_synthetic_and_not_mass_factors(self):
        record=self.report['lift_and_roof']
        self.assertEqual(record['counterweight_assumed_kg'],1315)
        self.assertEqual(record['permanent_equipment_assumed_kg'],2915)
        self.assertAlmostEqual(record['pit_rc_bottom_z_m'],-1.8)
        nominal=record['synthetic_load_envelopes'][0]
        self.assertAlmostEqual(nominal['alternative_head_or_buffer_envelope_kN'],2*(2915+700)*9.80665/1000)
        self.assertAlmostEqual(nominal['permanent_kN'],2915*9.80665/1000)
        self.assertEqual(record['load_application'],'NOT_APPLIED_TO_H02')

    def test_proposal_does_not_close_architecture_or_analysis(self):
        self.assertEqual(self.report['headroom']['sample_count'],468)
        self.assertEqual(self.report['headroom']['below_1_90_m'],0)
        self.assertFalse(self.report['architectural_acceptance'])
        self.assertFalse(self.report['structural_geometry_adopted'])
        self.assertFalse(self.report['solver_executed'])
        self.assertTrue(any('Ground discharge' in x for x in self.report['holds']))
        width=next(c for c in self.report['checks'] if c['id']=='H03-C08')
        self.assertEqual(width['status'],'PASS_PROPOSED_DIMENSIONS_ONLY')
        self.assertAlmostEqual(width['value']['margin_m'],.038)
        # A lower cap must fail the actual sampled clearance screen.
        bad=deepcopy(self.proposal);bad['lift_and_roof']['stair_cap_structural_top_z_m']=12.1
        result=evaluate(bad,self.basis,self.scheme,self.objects,self.levels,9.80665)
        self.assertGreater(result['headroom']['below_1_90_m'],0)


if __name__=='__main__':unittest.main()
