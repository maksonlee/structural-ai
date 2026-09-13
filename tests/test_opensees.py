"""Real-backend mechanics checks. Derivations are in docs/validation.md."""
import importlib.util
import math
import unittest

import numpy as np
from structural_ai.opensees_runner import build, configure, resultant, static_checks

AVAILABLE = importlib.util.find_spec('openseespy') is not None


def frame_model(direction=(1, 0, 0), local_y=(0, 1, 0), offset=(0, 0, 0)):
    return {
        'nodes': [{'id': 1, 'xyz': [2., 3., 1.]},
                  {'id': 2, 'xyz': (np.array([2., 3., 1.])+4*np.array(direction)).tolist()}],
        'supports': [{'node': 1, 'fixity': [1]*6}], 'nodal_masses': [],
        'materials': {'E_kN_m2': 25e6, 'poisson': .2},
        'sections': {'frame': {'A': .208, 'Iy': .004686933333333334,
                               'Iz': .002773333333333334, 'J': .006}},
        'elements': [{'id': 1, 'nodes': [1, 2], 'kind': 'frame', 'section': 'frame',
                      'local_y': list(local_y), 'offset': list(offset)}],
    }


def solve(ops, model, loads):
    model['load_cases'] = {'test': {'nodal_loads': loads}}
    xyz = build(ops, model)
    ops.timeSeries('Linear', 1)
    ops.pattern('Plain', 1, 1)
    for ld in loads:
        ops.load(ld['node'], *ld['vector'])
    configure(ops)
    if ops.analyze(1):
        raise AssertionError('Actual OpenSees analysis failed')
    return static_checks(ops, model, 'test', xyz)


class ResultantTests(unittest.TestCase):
    def test_position_and_applied_couple(self):
        actual = resultant({1: np.array([2., 3., 4.])}, [(1, [0., 5., 0., 1., 2., 3.])])
        np.testing.assert_allclose(actual, [0., 5., 0., -19., 2., 13.])

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            resultant({1: np.zeros(3)}, [(1, [math.nan]*6)])


@unittest.skipUnless(AVAILABLE, 'OpenSeesPy unavailable; mechanics NOT verified')
class OpenSeesTests(unittest.TestCase):
    def setUp(self):
        import openseespy.opensees as ops
        self.ops = ops

    def tearDown(self):
        self.ops.wipe()

    def test_frame_axes_signs_axial_biaxial_bending_and_torsion(self):
        for direction, y in [((1, 0, 0), (0, 1, 0)), ((0, 1, 0), (-1, 0, 0)),
                             ((0, 0, 1), (1, 0, 0))]:
            m = frame_model(direction, y)
            x, y = np.array(direction, dtype=float), np.array(y, dtype=float)
            z = np.cross(x, y)
            for vector, stiffness, bending in [(x, 25e6*m['sections']['frame']['A'], False),
                    (y, 25e6*m['sections']['frame']['Iz'], True),
                    (z, 25e6*m['sections']['frame']['Iy'], True)]:
                with self.subTest(direction=direction, load=vector):
                    check = solve(self.ops, m, [{'node': 2, 'vector': [*(10*vector), 0, 0, 0]}])
                    expected = 10*(4**3/3 if bending else 4)/stiffness
                    self.assertAlmostEqual(np.dot(self.ops.nodeDisp(2)[:3], vector)/expected, 1., places=8)
                    self.assertTrue(check['numerical_checks_passed'])
                    f = np.array(self.ops.eleResponse(1, 'localForce'))
                    local_index = 0 if np.array_equal(vector, x) else 1 if np.array_equal(vector, y) else 2
                    self.assertAlmostEqual(f[local_index], -10., places=7)
                    self.assertAlmostEqual(f[local_index+6], 10., places=7)
            check = solve(self.ops, m, [{'node': 2, 'vector': [0, 0, 0, *(10*x)]}])
            expected = 10*4/(25e6/2.4*.006)
            self.assertAlmostEqual(np.dot(self.ops.nodeDisp(2)[3:], x)/expected, 1., places=8)
            self.assertTrue(check['numerical_checks_passed'])

    def test_eccentric_offset_axial_load(self):
        m = frame_model(offset=(0, 0, -.35))
        check = solve(self.ops, m, [{'node': 2, 'vector': [10, 0, 0, 0, 0, 0]}])
        # At the offset centroid the nodal axial force also applies M_y=e*P.
        expected = 10*4/(25e6*.208)+10*.35**2*4/(25e6*m['sections']['frame']['Iy'])
        self.assertAlmostEqual(self.ops.nodeDisp(2)[0]/expected, 1., places=8)
        self.assertTrue(check['numerical_checks_passed'])

    def test_tip_mass_cantilever_eigenvalue_and_participation(self):
        m = frame_model()
        m['supports'].append({'node': 2, 'fixity': [1, 0, 1, 1, 1, 0]})
        m['nodal_masses'] = [{'node': 2, 'mass': [0, 2, 0, 0, 0, 0]}]
        build(self.ops, m)
        configure(self.ops)
        value = self.ops.eigen('-fullGenLapack', 1)[0]
        expected = 3*25e6*m['sections']['frame']['Iz']/4**3/2
        self.assertAlmostEqual(value/expected, 1., places=9)
        self.assertAlmostEqual(self.ops.modalProperties('-return')['partiMassRatiosMY'][0], 100., places=8)

    def test_shell_membrane_in_floor_and_wall_planes(self):
        for rotate in (False, True):
            coords = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]
            if rotate:
                coords = [(x, -z, y) for x, y, z in coords]
            # Permit Poisson contraction; suppress out-of-plane motion only.
            fixes = [[1, 1, 1, 0, 0, 0], [0, 1, 1, 0, 0, 0],
                     [0, 0, 1, 0, 0, 0], [1, 0, 1, 0, 0, 0]]
            if rotate:
                fixes = [[f[0], f[2], f[1], *f[3:]] for f in fixes]
            m = {'nodes': [{'id': i+1, 'xyz': list(p)} for i, p in enumerate(coords)],
                 'supports': [{'node': i+1, 'fixity': f} for i, f in enumerate(fixes)],
                 'nodal_masses': [], 'materials': {'E_kN_m2': 25e6, 'poisson': .2},
                 'sections': {'shell': {'t': .25}},
                 'elements': [{'id': 1, 'nodes': [1, 2, 3, 4], 'kind': 'shell', 'section': 'shell'}]}
            check = solve(self.ops, m, [{'node': n, 'vector': [5, 0, 0, 0, 0, 0]} for n in (2, 3)])
            self.assertTrue(check['numerical_checks_passed'])
            self.assertAlmostEqual(self.ops.nodeDisp(3)[0]/(10*2/(25e6*.25)), 1., places=8)
            stresses = np.array(self.ops.eleResponse(1, 'stresses')).reshape(4, 8)
            np.testing.assert_allclose(stresses[:, 0], 10., rtol=1e-8)
            np.testing.assert_allclose(stresses[:, 1:], 0., atol=1e-8)

    def test_shell_bending_square_plate_against_navier_series(self):
        # Simply supported square, uniform pressure. Navier thin-plate solution.
        q, a, t, E, nu = 1., 4., .02, 25e6, .2
        D = E*t**3/(12*(1-nu**2))
        expected = 16*q*a**4/(math.pi**6*D)*sum(
            math.sin(i*math.pi/2)*math.sin(j*math.pi/2)/(i*j*(i*i+j*j)**2)
            for i in range(1, 80, 2) for j in range(1, 80, 2))
        errors = []
        for n in (8, 16):
            node = lambda i, j: j*(n+1)+i+1
            m = {'nodes': [], 'supports': [], 'nodal_masses': [],
                 'materials': {'E_kN_m2': E, 'poisson': nu},
                 'sections': {'shell': {'t': t}}, 'elements': []}
            for j in range(n+1):
                for i in range(n+1):
                    tag = node(i, j)
                    m['nodes'].append({'id': tag, 'xyz': [a*i/n, a*j/n, 0.]})
                    m['supports'].append({'node': tag, 'fixity': [1, 1, int(i in (0,n) or j in (0,n)), 0, 0, 0]})
            loads = {p['id']: 0. for p in m['nodes']}
            for j in range(n):
                for i in range(n):
                    ns = [node(i,j),node(i+1,j),node(i+1,j+1),node(i,j+1)]
                    m['elements'].append({'id': len(m['elements'])+1, 'nodes': ns, 'kind': 'shell', 'section': 'shell'})
                    for tag in ns: loads[tag] -= q*(a/n)**2/4
            check = solve(self.ops, m, [{'node': k, 'vector': [0,0,v,0,0,0]} for k,v in loads.items()])
            actual = -self.ops.nodeDisp(node(n//2,n//2))[2]
            errors.append(abs(actual/expected-1))
            self.assertTrue(check['numerical_checks_passed'])
        self.assertLess(errors[1], errors[0])
        self.assertLess(errors[1], .02)
