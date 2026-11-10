# SPDX-License-Identifier: MIT

"""Small 4x4 matrix helpers (row-major lists of 16 numbers, like the machine_definition XML). Stdlib only."""

import math

IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def mul(a, b):
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


def translation(v):
    return [1.0, 0, 0, v[0], 0, 1.0, 0, v[1], 0, 0, 1.0, v[2], 0, 0, 0, 1.0]


def rot3(m3):
    """4x4 from a 3x3 (list of rows)."""
    return [m3[0][0], m3[0][1], m3[0][2], 0, m3[1][0], m3[1][1], m3[1][2], 0, m3[2][0], m3[2][1], m3[2][2], 0,
            0, 0, 0, 1.0]


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-12:
        raise ValueError("a direction must not be (0, 0, 0)")
    return [c / n for c in v]


def axis_angle(d, deg):
    """Rotation by deg about the direction d (Rodrigues), as a 3x3."""
    x, y, z = unit(d)
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    t = 1 - c
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]


def rotation_about(d, deg, pivot):
    """4x4: rotation by deg about the line through pivot with direction d."""
    r = axis_angle(d, deg)
    p = pivot
    t = [p[i] - sum(r[i][k] * p[k] for k in range(3)) for i in range(3)]
    return [r[0][0], r[0][1], r[0][2], t[0], r[1][0], r[1][1], r[1][2], t[1], r[2][0], r[2][1], r[2][2], t[2],
            0, 0, 0, 1.0]


def euler(rx, ry, rz):
    """3x3 of Rz(rz) * Ry(ry) * Rx(rx), angles in degrees."""
    def r(axis, deg):
        return axis_angle(axis, deg)
    def m(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return m(r([0, 0, 1], rz), m(r([0, 1, 0], ry), r([1, 0, 0], rx)))


def apply(m, p):
    return [m[r * 4] * p[0] + m[r * 4 + 1] * p[1] + m[r * 4 + 2] * p[2] + m[r * 4 + 3] for r in range(3)]


def apply_dir(m, v):
    return [m[r * 4] * v[0] + m[r * 4 + 1] * v[1] + m[r * 4 + 2] * v[2] for r in range(3)]


def origin(m):
    return [m[3], m[7], m[11]]
