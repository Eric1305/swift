import { BitmapLayer, type BitmapLayerProps } from '@deck.gl/layers';
import type { ShaderModule } from '@luma.gl/shadertools';
import type { DefaultProps } from '@deck.gl/core';

/**
 * Flood rendering from real terrain.
 *
 * Source: AWS Open Data "Terrarium" elevation tiles (USGS 3DEP in the US, ~10 m), no key.
 * decodeTile re-encodes each tile (R = normalized elevation, B = study-area mask). The shader
 * floods every pixel below `level` in a cartographic style: crisp anti-aliased shoreline with a
 * white edge and pale surf band, stepped depth bands (light cyan → deep blue) and thin contour
 * lines between bands.
 */
export const TERRARIUM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';

type FloodProps = { level: number; maxDepth: number; shore: number; band: number; base: number; range: number };

const floodModule = {
  name: 'flood',
  fs: /* glsl */ `\
layout(std140) uniform floodUniforms {
  float level;
  float maxDepth;
  float shore;
  float band;
  float base;
  float range;
} flood;
`,
  uniformTypes: { level: 'f32', maxDepth: 'f32', shore: 'f32', band: 'f32', base: 'f32', range: 'f32' },
} as const satisfies ShaderModule<FloodProps>;

const inject = {
  'fs:DECKGL_FILTER_COLOR': /* glsl */ `\
  float elev = flood.base + color.r * flood.range;
  float mask = color.b;
  float depth = flood.level - elev;
  // Screen-space width of 1 px in metres of depth; computed before any discard so the
  // derivative stays defined. Drives all the anti-aliasing below.
  float aa = max(fwidth(depth), 1e-4);
  float cover = smoothstep(-aa, aa, depth);
  if (cover <= 0.0 || mask <= 0.004) discard;

  // Stepped depth bands, like a printed bathymetry chart.
  float dpos = max(depth, 0.0);
  float bands = max(flood.maxDepth / flood.band, 1.0);
  float d = clamp(floor(dpos / flood.band) / bands, 0.0, 1.0);
  vec3 c0 = vec3(0.667, 0.890, 0.965);  // #AAE3F6 shallow
  vec3 c1 = vec3(0.290, 0.678, 0.906);  // #4AADE7
  vec3 c2 = vec3(0.137, 0.459, 0.812);  // #2375CF
  vec3 c3 = vec3(0.078, 0.294, 0.651);  // #144BA6 deep
  vec3 water = d < 0.33 ? mix(c0, c1, d / 0.33)
             : d < 0.66 ? mix(c1, c2, (d - 0.33) / 0.33)
             : mix(c2, c3, (d - 0.66) / 0.34);

  // Thin contour line at each band boundary.
  float f = fract(dpos / flood.band);
  float toLine = min(f, 1.0 - f) * flood.band;
  float contour = 1.0 - smoothstep(0.0, aa * 1.1, toLine);
  water = mix(water, water * 0.78, contour * step(flood.band * 0.5, dpos) * 0.7);

  // Pale surf band along the shore, then a crisp white shoreline.
  float surf = 1.0 - smoothstep(0.0, flood.shore, dpos);
  water = mix(water, vec3(0.890, 0.973, 1.0), surf * 0.75);
  float shoreline = 1.0 - smoothstep(aa * 0.6, aa * 2.2, dpos);
  water = mix(water, vec3(1.0), shoreline * 0.95);

  color = vec4(water, mask * color.a * cover * (0.80 + 0.15 * d));
`,
};

export type FloodLayerProps = BitmapLayerProps & {
  level: number;
  maxDepth: number;
  /** Depth (m) of the pale surf band along the shoreline. */
  shore?: number;
  /** Depth step (m) between color bands / contour lines. */
  band?: number;
  base: number;
  range: number;
};

const defaultProps: DefaultProps<FloodLayerProps> = {
  level: { type: 'number', value: -1e9 },
  maxDepth: { type: 'number', value: 3 },
  shore: { type: 'number', value: 0.12 },
  band: { type: 'number', value: 0.45 },
  base: { type: 'number', value: 0 },
  range: { type: 'number', value: 1 },
};

export class FloodBitmapLayer extends BitmapLayer<FloodLayerProps> {
  static layerName = 'FloodBitmapLayer';
  static defaultProps = defaultProps;

  getShaders() {
    const shaders = super.getShaders();
    return { ...shaders, modules: [...shaders.modules, floodModule], inject };
  }

  draw(opts: Parameters<BitmapLayer['draw']>[0]) {
    const { level, maxDepth, shore = 0.12, band = 0.45, base, range } = this.props;
    this.state.model?.shaderInputs.setProps({ flood: { level, maxDepth, shore, band, base, range } });
    super.draw(opts);
  }
}

export interface StudyArea {
  west: number;
  south: number;
  east: number;
  north: number;
  /** Fraction of the area width/height over which the flood fades out at the edges. */
  feather: number;
}

const smooth = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
/** Edge ramp over distance d inside the area; f = 0 gives a hard edge. */
const ramp = (d: number, f: number) => (f > 0 ? smooth(d / f) : d >= 0 ? 1 : 0);

export interface TerrainTile {
  image: ImageBitmap;
  /** Elevation (m) encoded as base + R/255 × range. */
  base: number;
  range: number;
  /** Elevation samples from fully inside the study area. */
  samples: Float32Array;
}

/**
 * Fetches a Terrarium tile and re-encodes it for the flood shader:
 * R = elevation normalized to the tile's own min..max (≈5 cm steps over Houston's relief;
 * one channel, so linear filtering stays correct), B = soft study-area mask, A = 255.
 */
export async function decodeTile(
  url: string,
  bbox: { west: number; south: number; east: number; north: number },
  area: StudyArea,
  signal?: AbortSignal,
): Promise<TerrainTile | null> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`terrain ${res.status}`);
  const bitmap = await createImageBitmap(await res.blob(), { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
  const { width: w, height: h } = bitmap;
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  const img = ctx.getImageData(0, 0, w, h);
  const px = img.data;

  const elev = new Float32Array(w * h);
  const mask = new Float32Array(w * h);
  const fx = (area.east - area.west) * area.feather;
  const fy = (area.north - area.south) * area.feather;
  const samples: number[] = [];
  let lo = Infinity;
  let hi = -Infinity;
  for (let j = 0; j < h; j++) {
    const lat = bbox.north - ((j + 0.5) / h) * (bbox.north - bbox.south);
    const my = Math.min(ramp(lat - area.south, fy), ramp(area.north - lat, fy));
    for (let i = 0; i < w; i++) {
      const lon = bbox.west + ((i + 0.5) / w) * (bbox.east - bbox.west);
      const p = j * w + i;
      const k = p * 4;
      const e = px[k] * 256 + px[k + 1] + px[k + 2] / 256 - 32768;
      const m = Math.min(my, ramp(lon - area.west, fx), ramp(area.east - lon, fx));
      elev[p] = e;
      mask[p] = m;
      if (m > 0) {
        if (e < lo) lo = e;
        if (e > hi) hi = e;
        if (m >= 1 && (i & 3) === 0 && (j & 3) === 0) samples.push(e);
      }
    }
  }
  if (lo === Infinity) return null; // tile entirely outside the study area
  smoothInPlace(elev, w, h, 2);

  const range = Math.max(0.5, hi - lo);
  for (let p = 0; p < w * h; p++) {
    const k = p * 4;
    px[k] = Math.round(Math.min(1, Math.max(0, (elev[p] - lo) / range)) * 255);
    px[k + 1] = 0;
    px[k + 2] = Math.round(mask[p] * 255);
    px[k + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return { image: canvas.transferToImageBitmap(), base: lo, range, samples: Float32Array.from(samples) };
}

/**
 * Two passes of a separable box blur (radius r) over the elevation grid. The 10 m DEM has
 * survey noise that turns depth contours into speckle; smoothing gives clean chart-like bands.
 */
function smoothInPlace(a: Float32Array, w: number, h: number, r: number) {
  const tmp = new Float32Array(a.length);
  const pass = (src: Float32Array, dst: Float32Array, horizontal: boolean) => {
    const n = horizontal ? w : h;
    const m = horizontal ? h : w;
    for (let line = 0; line < m; line++) {
      for (let i = 0; i < n; i++) {
        let sum = 0;
        let cnt = 0;
        for (let k = -r; k <= r; k++) {
          const j = Math.min(n - 1, Math.max(0, i + k));
          sum += src[horizontal ? line * w + j : j * w + line];
          cnt++;
        }
        dst[horizontal ? line * w + i : i * w + line] = sum / cnt;
      }
    }
  };
  for (let it = 0; it < 2; it++) {
    pass(a, tmp, true);
    pass(tmp, a, false);
  }
}

/** Value at quantile q (0–1) of a sorted array. */
export function quantile(sorted: Float32Array, q: number): number {
  if (!sorted.length) return NaN;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))));
  return sorted[i];
}
