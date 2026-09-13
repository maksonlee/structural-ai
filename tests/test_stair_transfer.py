"""Independent geometry/statics and real OpenSees checks for H02 gravity transfer."""
from collections import defaultdict
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import yaml

from structural_ai.coordination import read_geometry
from structural_ai.model_builder import create
from structural_ai.stair_transfer import reactions, plane_weights
from structural_ai.handoff import proposal_checks
from structural_ai.cli import load_project, received_scheme

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT/'project/structural/inputs'
SCHEME = ROOT/'project/architect/outputs/scheme.yaml'


class StripTests(unittest.TestCase):
    def test_eccentric_and_reversed_load_rejected(self):
        np.testing.assert_allclose(reactions(12., 4., 2., 8.), [8., 4.])
        for inputs in [(12., 9., 2., 8.), (12., 4., 8., 2.), (-1., 4., 2., 8.)]:
            with self.assertRaises(ValueError):
                reactions(*inputs)

    def test_off_grid_wall_projection_preserves_position(self):
        nodes = [{'id': i+1, 'xyz': p} for i, p in enumerate(
            [[5., 2., 0.], [5., 6., 0.], [5., 2., 3.], [5., 6., 3.]])]
        result = dict(plane_weights(nodes, [5., 3., 2.]))
        np.testing.assert_allclose([result[i] for i in range(1, 5)], [.25, 1/12, .5, 1/6])
        np.testing.assert_allclose(sum(np.array(n['xyz'])*result[n['id']] for n in nodes), [5, 3, 2])
        with self.assertRaises(ValueError):
            plane_weights(nodes[:-1], [5., 3., 2.])
        with self.assertRaises(ValueError):
            plane_weights(nodes, [5., 7., 2.])

    @unittest.skipUnless(importlib.util.find_spec('openseespy'), 'Actual OpenSees backend unavailable')
    def test_real_opensees_eccentric_strip_reactions(self):
        # Independent 6 m pin/roller strip with a 12 kN force 2 m from its left end.
        # This verifies the released-strip support idealization, not RC capacity.
        import openseespy.opensees as ops
        try:
            ops.wipe(); ops.model('basic', '-ndm', 2, '-ndf', 3)
            for tag, x in [(1, 2.), (2, 4.), (3, 8.)]: ops.node(tag, x, 1.)
            ops.fix(1, 1, 1, 0); ops.fix(3, 0, 1, 0)
            ops.geomTransf('Linear', 1)
            for tag, a, b in [(1, 1, 2), (2, 2, 3)]:
                ops.element('elasticBeamColumn', tag, a, b, .18, 25e6, .18**3/12, 1)
            ops.timeSeries('Linear', 1); ops.pattern('Plain', 1, 1)
            ops.load(2, 0., -12., 0.)
            ops.system('BandGeneral'); ops.numberer('RCM'); ops.constraints('Plain')
            ops.integrator('LoadControl', 1.); ops.algorithm('Linear'); ops.analysis('Static')
            self.assertEqual(ops.analyze(1), 0)
            ops.reactions()
            actual = [ops.nodeReaction(n, 2) for n in (1, 3)]
            np.testing.assert_allclose(actual, [8., 4.], rtol=1e-9, atol=1e-9)
            np.testing.assert_allclose(actual, reactions(12., 4., 2., 8.), rtol=1e-9)
            # Max moment at the eccentric point: R_left * 2 = 16 kNm.
            self.assertAlmostEqual(abs(ops.eleResponse(1, 'localForce')[-1]), 16., places=7)
        finally:
            ops.wipe()


@unittest.skipUnless(importlib.util.find_spec('ifcopenshell'), 'Independent source geometry unavailable')
class BuildingStairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)
        directory,project,_,_,_=load_project(ROOT/'project')
        received=received_scheme(directory,project)
        historical=ROOT/'tests/fixtures/h02-analysis.yaml'
        config=historical if historical.exists() else INPUT/'analysis.yaml'
        with redirect_stdout(io.StringIO()):
            cls.model = create(received, config, cls.out, architect_scheme=SCHEME)
        cls.transfer = json.loads((cls.out/'stair_transfer.json').read_text())
        _, cls.objects, _, _, _, cls.levels = read_geometry(received)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_source_centroids_and_bearing_deduction(self):
        for s in self.transfer['sources']:
            with self.subTest(source=s['source_name']):
                measure = s['measure']; o = self.objects[s['source_name']]
                self.assertEqual(s['source_guid'], o['guid'])
                self.assertAlmostEqual(measure['gross_volume_m3'], o['gross_m3'], places=8)
                if s['source_name'].startswith('STF-'):
                    np.testing.assert_allclose(measure['gross_centroid_m'], o['centroid_m'], atol=1e-8)
                    # Rectangular overlap independently measured from source bounds.
                    self.assertAlmostEqual(measure['upper_bearing_overlap_m3'], .15*.18*1.3, places=9)
                    self.assertAlmostEqual(measure['owned_volume_m3'], o['gross_m3']-.0351, places=9)

    def test_candidate_development_preserves_adopted_h02_signature(self):
        import hashlib
        fixture=json.loads((Path(__file__).parent/'fixtures/h02_input_signature.json').read_text())
        canonical=json.dumps({k:self.model[k] for k in fixture['signature_keys']},
                             sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),fixture['canonical_input_signature_sha256'])

    def test_stair_weight_moments_and_mass(self):
        xyz = {n['id']: np.array(n['xyz']) for n in self.model['nodes']}
        area = sum(s['horizontal_loaded_area_m2'] for s in self.transfer['sources'])
        self.assertAlmostEqual(area, 2*1.3*3.6+4*1.3*3.3+2.8*(1.4+1.7+1.7), places=8)
        for s in self.transfer['sources']:
            for c in s['components']:
                weight = c['weight_kN']; centre = c['physical_centroid_m']
                force = sum(n['downward_kN'] for n in c['receiving_nodes'])
                first = sum(n['downward_kN']*xyz[n['node']][:2] for n in c['receiving_nodes'])
                self.assertAlmostEqual(force, weight, places=8)
                np.testing.assert_allclose(first, weight*np.array(centre[:2]), atol=1e-7)
        self.assertEqual(len(self.model['load_only_mapping']), 9)
        weight = -sum(ld['vector'][2] for case in ('D_SELF','D_SUPER','L_PARTITION')
                      for ld in self.model['load_cases'][case]['nodal_loads'])
        mass = sum(n['mass'][0] for n in self.model['nodal_masses'])
        self.assertAlmostEqual(mass*self.model['materials']['g_m_s2'], weight, places=6)

    def test_landings_use_actual_resultant_and_upper_interface(self):
        records = {s['source_name']: s for s in self.transfer['sources']}
        for st, y in [('1F', 10.45), ('2F', 10.3), ('3F', 10.3)]:
            self.assertAlmostEqual(records['STL-'+st+'-MID']['measure']['centroid_m'][1], y)
        for st in ('2F', '3F'):
            points = records['STF-'+st+'-A']['components'][0]['support_reactions']
            self.assertIn(9.45, [round(p['xyz_m'][1], 7) for p in points])

    def test_equipment_and_stair_holds_survive_dimensional_screen(self):
        report=proposal_checks(yaml.safe_load(SCHEME.read_text()), self.objects, self.levels)
        self.assertFalse(report['architectural_acceptance'])
        self.assertFalse(report['final_design_complete'])
        self.assertAlmostEqual(report['lift']['pit_bottom_reservation_z_m'], -1.45)
        self.assertAlmostEqual(report['lift']['minimum_overhead_soffit_z_m'], 11.95)
        np.testing.assert_allclose(report['lift']['nominal_dimension_margin_m'], [.23,.13], atol=1e-8)
        self.assertIn('HOLD', report['stairs']['status'])
        self.assertLess(report['occupied_reservation_area_per_level_m2'], 200.)
