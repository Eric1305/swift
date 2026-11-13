import type { LonLat } from '../data/types';

/**
 * A unit house for deck.gl's SimpleMeshLayer: 1 × 1 footprint (x along the ridge, y across),
 * walls up to WALL_TOP, a pitched gable roof up to 1 with a small eave overhang.
 * Flat-shaded (each triangle has its own vertices + normal) so the lighting gives crisp
 * planes: sunlit roof slope, shaded slope, distinct gable ends — a house, not a block.
 * Walls and roof are separate meshes so the roof can carry the status color on its own.
 */
const WALL_TOP = 0.62;
const OVERHANG = 0.07;
const RIDGE = 1;

type V3 = [number, number, number];
interface Mesh {
  attributes: { positions: { value: Float32Array; size: 3 }; normals: { value: Float32Array; size: 3 } };
}

function sub(a: V3, b: V3): V3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}
function cross(a: V3, b: V3): V3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
function norm(a: V3): V3 {
  const l = Math.hypot(a[0], a[1], a[2]) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
}

function build(tris: [V3, V3, V3][]): Mesh {
  const pos: number[] = [];
  const nrm: number[] = [];
  for (const [a, b, c] of tris) {
    const n = norm(cross(sub(b, a), sub(c, a)));
    pos.push(...a, ...b, ...c);
    nrm.push(...n, ...n, ...n);
  }
  return {
    attributes: {
      positions: { value: new Float32Array(pos), size: 3 },
      normals: { value: new Float32Array(nrm), size: 3 },
    },
  };
}

/** Counter-clockwise quad (seen from outside) → two triangles. */
const quad = (a: V3, b: V3, c: V3, d: V3): [V3, V3, V3][] => [
  [a, b, c],
  [a, c, d],
];

const h = 0.5;
const w = WALL_TOP;

export const WALLS_MESH = build([
  // long walls (y = ±0.5)
  ...quad([-h, -h, 0], [h, -h, 0], [h, -h, w], [-h, -h, w]),
  ...quad([h, h, 0], [-h, h, 0], [-h, h, w], [h, h, w]),
  // short walls (x = ±0.5) with gable triangles up to the ridge
  ...quad([h, -h, 0], [h, h, 0], [h, h, w], [h, -h, w]),
  [[h, -h, w], [h, h, w], [h, 0, RIDGE]],
  ...quad([-h, h, 0], [-h, -h, 0], [-h, -h, w], [-h, h, w]),
  [[-h, h, w], [-h, -h, w], [-h, 0, RIDGE]],
]);

const o = OVERHANG;
const slope = (RIDGE - WALL_TOP) / h; // rise per unit run
const eaveZ = WALL_TOP - o * slope;
export const ROOF_MESH = build([
  // south slope (faces -y)
  ...quad([-h - o, -h - o, eaveZ], [h + o, -h - o, eaveZ], [h + o, 0, RIDGE], [-h - o, 0, RIDGE]),
  // north slope (faces +y)
  ...quad([h + o, h + o, eaveZ], [-h - o, h + o, eaveZ], [-h - o, 0, RIDGE], [h + o, 0, RIDGE]),
]);

const M_PER_DEG_LAT = 110_540;

export interface HouseFrame {
  center: LonLat;
  /** metres along the ridge (longest footprint edge) */
  length: number;
  /** metres across */
  width: number;
  /** degrees, counter-clockwise from east, for SimpleMeshLayer getOrientation yaw */
  yaw: number;
}

/** Oriented frame of a footprint: ridge along its longest edge, extents projected onto it. */
export function houseFrame(ring: LonLat[]): HouseFrame {
  const pts = ring.slice(0, -1);
  const lat0 = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const lon0 = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const mx = 111_320 * Math.cos((lat0 * Math.PI) / 180);
  const xy = pts.map(([lon, lat]) => [(lon - lon0) * mx, (lat - lat0) * M_PER_DEG_LAT] as const);

  let best = 0;
  let angle = 0;
  for (let i = 0; i < xy.length; i++) {
    const a = xy[i];
    const b = xy[(i + 1) % xy.length];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len > best) {
      best = len;
      angle = Math.atan2(b[1] - a[1], b[0] - a[0]);
    }
  }
  const ux = Math.cos(angle);
  const uy = Math.sin(angle);
  let minU = Infinity, maxU = -Infinity, minV = Infinity, maxV = -Infinity;
  for (const [x, y] of xy) {
    const u = x * ux + y * uy;
    const v = -x * uy + y * ux;
    minU = Math.min(minU, u); maxU = Math.max(maxU, u);
    minV = Math.min(minV, v); maxV = Math.max(maxV, v);
  }
  const cu = (minU + maxU) / 2;
  const cv = (minV + maxV) / 2;
  const cx = cu * ux - cv * uy;
  const cy = cu * uy + cv * ux;
  return {
    center: [lon0 + cx / mx, lat0 + cy / M_PER_DEG_LAT],
    length: Math.max(4, maxU - minU),
    width: Math.max(4, maxV - minV),
    yaw: (angle * 180) / Math.PI,
  };
}

/** Wall-top height of a house mesh scaled to `ridge` metres. */
export const wallTop = (ridge: number) => ridge * WALL_TOP;
