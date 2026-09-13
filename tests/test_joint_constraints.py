"""Known-solution checks of eccentric MPC statics and condensed inertia."""
from copy import deepcopy
import importlib.util
import unittest
import numpy as np
from structural_ai.joint_constraints import rigid_transform, validate_constraints
from structural_ai.opensees_runner import build, configure, static_checks


def model():
    return {
        'nodes': [{'id': 1, 'xyz': [0., 0., 0.]}, {'id': 2, 'xyz': [0., 0., 3.]},
                  {'id': 3, 'xyz': [.3, -.2, 3.]}],
        'supports': [{'node': 1, 'fixity': [1]*6}],
        'materials': {'E_kN_m2': 25e6, 'poisson': .2},
        'sections': {'column': {'A': .36, 'Iy': .0108, 'Iz': .0108, 'J': .018}},
        'elements': [{'id': 1, 'kind': 'frame', 'nodes': [1, 2], 'section': 'column',
                      'local_y': [1., 0., 0.]}],
        'rigid_joints': [{'master': 2, 'slave': 3, 'type': 'beam'}], 'nodal_masses': [],
    }


def flexibility():
    # Exact Euler-Bernoulli tip flexibility for a vertical member; DOFs X,Y,Z,RX,RY,RZ.
    length, e, g, area, inertia, torsion = 3., 25e6, 25e6/2.4, .36, .0108, .018
    matrix = np.diag([length**3/(3*e*inertia)]*2 + [length/(e*area)] +
                     [length/(e*inertia)]*2 + [length/(g*torsion)])
    matrix[0, 4] = matrix[4, 0] = length**2/(2*e*inertia)
    matrix[1, 3] = matrix[3, 1] = -length**2/(2*e*inertia)
    return matrix


class JointConstraintTests(unittest.TestCase):
    def tearDown(self):
        if importlib.util.find_spec('openseespy'):
            import openseespy.opensees as ops
            ops.wipe()

    def test_virtual_work_and_eccentric_moment_signs(self):
        transform = rigid_transform([.3, -.2, .1])
        motion = np.array([.01, -.02, .03, .004, .005, -.006])
        force = np.array([7., -11., -13., 2., 3., 5.])
        np.testing.assert_allclose((transform @ motion)[:3],
                                   motion[:3] + np.cross(motion[3:], [.3, -.2, .1]))
        np.testing.assert_allclose((transform.T @ force)[3:],
                                   force[3:] + np.cross([.3, -.2, .1], force[:3]))
        self.assertAlmostEqual(force @ transform @ motion, (transform.T @ force) @ motion)

    def test_chain_repeated_slave_and_fixed_node_rejected(self):
        original = model()
        xyz = {n['id']: np.array(n['xyz']) for n in original['nodes']}
        for extra in ({'master': 3, 'slave': 2}, {'master': 2, 'slave': 3},
                      {'master': 1, 'slave': 3}):
            trial = deepcopy(original)
            trial['rigid_joints'].append(extra)
            with self.assertRaises(ValueError):
                validate_constraints(trial, xyz)

    @unittest.skipUnless(importlib.util.find_spec('openseespy'), 'Actual OpenSees backend unavailable')
    def test_real_eccentric_joint_static_flexibility_and_force_recovery(self):
        import openseespy.opensees as ops
        m = model()
        force = np.array([7., -11., -13., 2., 3., 5.])
        m['load_cases'] = {'test': {'nodal_loads': [{'node': 3, 'vector': force.tolist()}]}}
        xyz = build(ops, m)
        ops.timeSeries('Linear', 1); ops.pattern('Plain', 1, 1); ops.load(3, *force)
        configure(ops, m)
        self.assertEqual(ops.analyze(1), 0)
        equivalent = force.copy()
        equivalent[3:] += np.cross([.3, -.2, 0.], force[:3])
        expected = flexibility() @ equivalent
        np.testing.assert_allclose(ops.nodeDisp(2), expected, rtol=1e-10, atol=1e-14)
        np.testing.assert_allclose(ops.nodeDisp(3)[:3], expected[:3] +
                                   np.cross(expected[3:], [.3, -.2, 0.]), atol=1e-14)
        result = static_checks(ops, m, 'test', xyz)
        self.assertTrue(result['numerical_checks_passed'])
        np.testing.assert_allclose(result['joint_actions'][0]['force_on_slave_kN_kNm'], -force)
        np.testing.assert_allclose(result['joint_actions'][0]['force_on_master_kN_kNm'], equivalent)

    @unittest.skipUnless(importlib.util.find_spec('openseespy'), 'Actual OpenSees backend unavailable')
    def test_real_eccentric_mass_six_eigenvalues_and_participation(self):
        import openseespy.opensees as ops
        m = model()
        root_mass = np.array([1., 1., 1., .1, .2, .3])
        slave_mass = np.array([2., 2., 2., 0., 0., 0.])
        m['nodal_masses'] = [{'node': 2, 'mass': root_mass.tolist()},
                             {'node': 3, 'mass': slave_mass.tolist()}]
        build(ops, m); configure(ops, m)
        actual = np.array(ops.eigen('-fullGenLapack', 6))
        transform = rigid_transform([.3, -.2, 0.])
        # Analytical 6-DOF tip system, not another discretized building solver.
        mass = np.diag(root_mass) + transform.T @ np.diag(slave_mass) @ transform
        expected = np.sort(np.linalg.eigvals(np.linalg.solve(mass, np.linalg.inv(flexibility()))).real)
        np.testing.assert_allclose(actual, expected, rtol=1e-10)
        properties = ops.modalProperties('-return')
        for index in range(6):
            root_phi, slave_phi = np.array(ops.nodeEigenvector(2, index+1)), np.array(ops.nodeEigenvector(3, index+1))
            np.testing.assert_allclose(slave_phi, transform @ root_phi, atol=1e-10)
            gm = sum(root_mass*root_phi**2 + slave_mass*slave_phi**2)
            influence = (root_mass*root_phi + slave_mass*slave_phi)[:3]
            ratio = influence**2 / gm / 3 * 100
            upstream = [properties['partiMassRatios'+axis][index] for axis in ('MX', 'MY', 'MZ')]
            np.testing.assert_allclose(ratio, upstream, atol=1e-8)

    @unittest.skipUnless(importlib.util.find_spec('openseespy'), 'Actual OpenSees backend unavailable')
    def test_real_frame_wall_patch_axial_sharing(self):
        import openseespy.opensees as ops
        # The rigid cross-section restrains the shell's transverse Poisson strain.
        # Its axial membrane modulus is E/(1-nu^2); this is not an unconfined prism.
        for nu in (0., .2):
            m=model();m['materials']['poisson']=nu
            m['nodes']=[{'id':1,'xyz':[0.,0.,0.]},{'id':2,'xyz':[0.,0.,3.]},
                        {'id':3,'xyz':[.335,-.3,0.]},{'id':4,'xyz':[.335,.3,0.]},
                        {'id':5,'xyz':[.335,.3,3.]},{'id':6,'xyz':[.335,-.3,3.]}]
            m['supports']=[{'node':n,'fixity':[1]*6} for n in (1,3,4)]
            m['sections']['wall']={'t':.07}
            m['elements'].append({'id':2,'kind':'shell','nodes':[3,4,5,6],'section':'wall'})
            m['rigid_joints']=[{'master':2,'slave':n,'type':'beam'} for n in (5,6)]
            wall_area=.6*.07;column_area=.36
            wall_fraction=(wall_area/(1-nu**2))/(column_area+wall_area/(1-nu**2))
            force=np.array([0.,0.,-100.,0.,100*.335*wall_fraction,0.])
            m['load_cases']={'test':{'nodal_loads':[{'node':2,'vector':force.tolist()}]}}
            xyz=build(ops,m);ops.timeSeries('Linear',1);ops.pattern('Plain',1,1);ops.load(2,*force)
            configure(ops,m);self.assertEqual(ops.analyze(1),0)
            expected=-100*3/(25e6*(column_area+wall_area/(1-nu**2)))
            self.assertAlmostEqual(ops.nodeDisp(2)[2]/expected,1.,places=9)
            np.testing.assert_allclose(np.array(ops.nodeDisp(2))[[0,1,3,4,5]],0.,atol=1e-12)
            frame=np.array(ops.eleResponse(1,'localForce'))
            self.assertAlmostEqual(frame[6],-100*(1-wall_fraction),places=7)
            self.assertTrue(static_checks(ops,m,'test',xyz)['numerical_checks_passed'])


if __name__ == '__main__':
    unittest.main()
