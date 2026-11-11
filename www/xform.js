// SPDX-License-Identifier: MIT
// Pure matrix math for dragging in the 3D preview (no three.js, no DOM): the world-space result of a drag is converted
// into the frame the value is STORED in (finding R1: matrices, positions and pivots are in the LOCAL frame of the
// enclosing node). Matrices are row-major lists of 16 numbers, like the project document and the XML.
// Mirrored in Python (tests/test_xform.py checks the same cases against the XML evaluator) and exercised in the browser
// by tests/ui/ui_check.py through window.__mb.xform.

export const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

export function mul(a, b) {
  const r = new Array(16);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
    let s = 0;
    for (let k = 0; k < 4; k++) s += a[i * 4 + k] * b[k * 4 + j];
    r[i * 4 + j] = s;
  }
  return r;
}

// Inverse of an affine matrix (last row 0, 0, 0, 1): the 3x3 part is inverted with the cofactors, so a scaled matrix works too.
export function inverse(m) {
  const a = [[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]];
  const det = a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0]) + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]);
  if (Math.abs(det) < 1e-18) throw new Error("the parent frame is singular");
  const inv = [0, 1, 2].map((r) => [0, 1, 2].map((c) =>
    (a[(c + 1) % 3][(r + 1) % 3] * a[(c + 2) % 3][(r + 2) % 3] - a[(c + 1) % 3][(r + 2) % 3] * a[(c + 2) % 3][(r + 1) % 3]) / det));
  const t = [m[3], m[7], m[11]];
  const out = [];
  for (let r = 0; r < 3; r++) {
    out.push(inv[r][0], inv[r][1], inv[r][2], -(inv[r][0] * t[0] + inv[r][1] * t[1] + inv[r][2] * t[2]));
  }
  return out.concat([0, 0, 0, 1]);
}

// The matrix of a node in its parent's frame, from its world matrix and the parent's world matrix.
export const localMatrix = (parentWorld, world) => mul(inverse(parentWorld), world);
export const worldMatrix = (parentWorld, local) => mul(parentWorld, local);

export function applyPoint(m, p) {
  return [0, 1, 2].map((r) => m[r * 4] * p[0] + m[r * 4 + 1] * p[1] + m[r * 4 + 2] * p[2] + m[r * 4 + 3]);
}
// A world point as the parent frame sees it (a pivot, a tool position).
export const localPoint = (parentWorld, p) => applyPoint(inverse(parentWorld), p);

// 4x4 from a 3x3 (list of rows), a position and a scale (T * R * S, as in the project's matrices)
export function fromParts(pos, rot3, scale = [1, 1, 1]) {
  const m = [];
  for (let r = 0; r < 3; r++) m.push(rot3[r][0] * scale[0], rot3[r][1] * scale[1], rot3[r][2] * scale[2], pos[r]);
  return m.concat([0, 0, 0, 1]);
}

const clean = (v, step) => { const r = Math.round(v / step) * step; return Math.abs(r) < step / 2 ? 0 : +r.toFixed(12); };
// Values to save: positions to 1e-6 mm, the rotation/scale part to 1e-9 (so a 10 mm snap is exactly 10, not 9.999999999997).
export const cleanVec = (v) => v.map((c) => clean(c, 1e-6));
export function cleanMatrix(m) {
  return m.map((c, i) => (i === 3 || i === 7 || i === 11 ? clean(c, 1e-6) : i >= 12 ? (i === 15 ? 1 : 0) : clean(c, 1e-9)));
}
