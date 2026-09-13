"""Small-rotation eccentric joints and work-conjugate force recovery.

This is an OpenSees input/check boundary, not a stiffness assembler or solver.
Each slave has one unconstrained master; constraint chains are rejected.
"""
import numpy as np


def rigid_transform(offset):
    """u_slave = T u_master, with translation = u + theta cross offset."""
    x, y, z = np.asarray(offset, dtype=float)
    if not np.isfinite([x, y, z]).all():
        raise ValueError('Nonfinite rigid-joint offset')
    matrix = np.eye(6)
    matrix[:3, 3:] = [[0., z, -y], [-z, 0., x], [y, -x, 0.]]
    return matrix


def validate_constraints(model, xyz):
    links = model.get('rigid_joints', [])
    slaves = [link['slave'] for link in links]
    masters = {link['master'] for link in links}
    fixed = {s['node'] for s in model['supports'] if any(s['fixity'])}
    if len(slaves) != len(set(slaves)) or masters.intersection(slaves):
        raise ValueError('Repeated slave or chained rigid joint')
    if fixed.intersection(slaves) or fixed.intersection(masters):
        raise ValueError('Fixed joint nodes must use direct fixity, not multiple constraints')
    for link in links:
        if link['master'] not in xyz or link['slave'] not in xyz:
            raise ValueError('Unknown rigid-joint node')
        if link.get('type', 'beam') != 'beam':
            raise ValueError('Only six-DOF small-rotation beam joints are implemented')
        rigid_transform(xyz[link['slave']] - xyz[link['master']])
    return links


def recover_constraints(model, xyz, nodal, displacements):
    """Reduce Fe-Fext-R by virtual work; retain physical joint force pairs.

    A slave residual q is the joint action on that slave. The master receives
    -T.T q, including eccentric moments. The reduced residual must vanish.
    """
    reduced = {node: vector.copy() for node, vector in nodal.items()}
    actions = []
    error = np.zeros(6)
    for link in validate_constraints(model, xyz):
        master, slave = link['master'], link['slave']
        transform = rigid_transform(xyz[slave] - xyz[master])
        force = nodal[slave].copy()
        transferred = transform.T @ force
        reduced[master] += transferred
        reduced[slave] *= 0.
        error = np.maximum(error, abs(displacements[slave] - transform @ displacements[master]))
        actions.append({'master': master, 'slave': slave,
                        'force_on_slave_kN_kNm': force.tolist(),
                        'force_on_master_kN_kNm': (-transferred).tolist()})
    return reduced, actions, error
