"""Small coordinate helpers shared with Blender (no bpy or analysis dependencies).

Matrices are row-major affine 4x4; points and lengths are LDraw units throughout.
"""

import math


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def mul(a, s):
    return [x * s for x in a]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = length(a)
    if n < 1e-10:
        raise ValueError("Zero-length direction or parallel frame axes")
    return mul(a, 1 / n)


def identity():
    return [[float(i == j) for j in range(4)] for i in range(4)]


def matmul(a, b):
    return [
        [sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)
    ]


def point(m, p):
    return [sum(m[i][j] * p[j] for j in range(3)) + m[i][3] for i in range(3)]


def direction(m, p):
    return [sum(m[i][j] * p[j] for j in range(3)) for i in range(3)]


def pose(position, rotation):
    return [list(rotation[i]) + [position[i]] for i in range(3)] + [
        [0.0, 0.0, 0.0, 1.0]
    ]


def inverse(m):
    # General affine inverse: source rotations are sometimes rounded or mirrored.
    a, b, c = [row[:3] for row in m[:3]]
    det = dot(a, cross(b, c))
    if abs(det) < 1e-12:
        raise ValueError("Singular transform")
    columns = [
        mul(cross(b, c), 1 / det),
        mul(cross(c, a), 1 / det),
        mul(cross(a, b), 1 / det),
    ]
    r = [list(row) for row in zip(*columns)]
    return pose([-dot(row, [m[i][3] for i in range(3)]) for row in r], r)


def frame(origin, axis, hint=None):
    z = unit(axis)
    if hint is None:
        hint = min(([1, 0, 0], [0, 1, 0], [0, 0, 1]), key=lambda v: abs(dot(z, v)))
    x = unit(sub(hint, mul(z, dot(hint, z))))
    y = cross(z, x)
    return pose(origin, list(zip(x, y, z)))


def rotation_z(angle):
    c, s = math.cos(angle), math.sin(angle)
    return pose([0, 0, 0], [[c, -s, 0], [s, c, 0], [0, 0, 1]])


def path_sample(rows, t):
    """Cyclic piecewise-linear [u, v, angle] lookup of a `path` body table.

    Rows are evenly spaced one parameter unit apart; the period is len(rows) - 1,
    so the last row closes the loop (same translation, angle may add 2*pi*k).
    """
    period = len(rows) - 1
    t = t - period * math.floor(t / period)
    i = min(int(math.floor(t)), period - 1)
    f = t - i
    a, b = rows[i], rows[i + 1]
    return [a[k] + (b[k] - a[k]) * f for k in range(3)]


def delta(frame_matrix, kind, value):
    if kind == "path":
        # Planar pose in the body frame: translate (u, v) in local XY, then turn about local Z.
        u, v, angle = value
        m = rotation_z(angle)
        m[0][3], m[1][3] = u, v
        return matmul(matmul(frame_matrix, m), inverse(frame_matrix))
    m = rotation_z(value) if kind == "revolute" else identity()
    if kind == "prismatic":
        m[2][3] = value
    elif kind == "stretch":
        # Coil springs only: scale along the declared axis about the origin.
        m[2][2] = value
    return matmul(matmul(frame_matrix, m), inverse(frame_matrix))


def pitch_radius(teeth, pitch=8.0):
    if teeth <= 0 or pitch <= 0:
        raise ValueError("Gear tooth count and pitch must be positive")
    return teeth * pitch / (2 * math.pi)


def signed_gear_ratio(a_axis, a_center, a_teeth, b_axis, b_center, b_teeth):
    """Adapted from the supplied F1 rig: match tangent velocity at pitch contact."""
    aa, ba = unit(a_axis), unit(b_axis)
    d = sub(b_center, a_center)
    toward = unit(sub(d, mul(aa, dot(d, aa))))
    p = add(a_center, mul(toward, pitch_radius(a_teeth)))
    lever = dot(cross(ba, sub(p, b_center)), cross(aa, toward))
    if abs(lever) < 1e-9:
        raise ValueError("Degenerate gear contact; inspect axes and centres")
    pitch_radius(b_teeth)
    return math.copysign(a_teeth / b_teeth, lever)


def rack_ratio(axis, center, teeth, rack_point, slide):
    a, s = unit(axis), unit(slide)
    d = sub(rack_point, center)
    toward = unit(sub(d, mul(a, dot(d, a))))
    return pitch_radius(teeth) * dot(cross(a, toward), s)
