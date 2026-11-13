import { BitmapLayer, type BitmapLayerProps } from '@deck.gl/layers';
import type { ShaderModule } from '@luma.gl/shadertools';
import type { DefaultProps } from '@deck.gl/core';

/**
 * Flood rendering from real terrain.
 *
 * Source: AWS Open Data "Terrarium" elevation tiles (USGS 3DEP in the US, ~10 m), no key.
 * Each pixel encodes metres as R*256 + G + B/256 − 32768. The shader floods every pixel
 * below `level`, colors it by depth (shallow cyan → deep blue) and feathers the shoreline.
 * Pixels outside the study area arrive with alpha already faded to 0 (see decodeTile).
 */
export const TERRARIUM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';

type FloodProps = { level: number; maxDepth: number; shore: number; base: number; range: number };

const floodModule = {
  name: 'flood',
  fs: /* glsl */ `\
layout(std140) uniform floodUniforms {
  float level;
  float maxDepth;
  float shore;
  float base;
  float range;
} flood;
`,
  uniformTypes: { level: 'f32', maxDepth: 'f32', shore: 'f32', base: 'f32', range: 'f32' },
} as const satisfies ShaderModule<FloodProps>;

const inject = {
  'fs:DECKGL_FILTER_COLOR': /* glsl */ `\
  // Texel (see decodeTile): R = elevation normalized to this tile's [base, base+range],
  // B = study-area mask. Alpha is always opaque so the browser never premultiplies RGB away.
  float elev = flood.base + color.r * flood.range;
  float mask = color.b;
  float depth = flood.level - elev;
  if (depth <= 0.0 || mask <= 0.004) discard;
  float d = clamp(depth / max(flood.maxDepth, 0.1), 0.0, 1.0);
  vec3 shallow = vec3(0.553, 0.835, 0.925);  // #8DD5EC
  vec3 mid     = vec3(0.243, 0.616, 0.867);  // #3E9DDD
  vec3 deep    = vec3(0.090, 0.290, 0.600);  // #174A99
  vec3 water = d < 0.5 ? mix(shallow, mid, d * 2.0) : mix(mid, deep, (d - 0.5) * 2.0);
  float edge = smoothstep(0.0, flood.shore, depth);
  color = vec4(water, mask * color.a * edge * (0.42 + 0.4 * d));
`,
};

export type FloodLayerProps = BitmapLayerProps & { level: number; maxDepth: number; shore?: number; base: number; range: number };

const defaultProps: DefaultProps<FloodLayerProps> = {
  level: { type: 'number', value: -1e9 },
  maxDepth: { type: 'number', value: 3 },
  shore: { type: 'number', value: 0.25 },
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
    const { level, maxDepth, shore = 0.25, base, range } = this.props;
    this.state.model?.shaderInputs.setProps({ flood: { level, maxDepth, shore, base, range } });
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
    const my = Math.min(smooth((lat - area.south) / fy), smooth((area.north - lat) / fy));
    for (let i = 0; i < w; i++) {
      const lon = bbox.west + ((i + 0.5) / w) * (bbox.east - bbox.west);
      const p = j * w + i;
      const k = p * 4;
      const e = px[k] * 256 + px[k + 1] + px[k + 2] / 256 - 32768;
      const m = Math.min(my, smooth((lon - area.west) / fx), smooth((area.east - lon) / fx));
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

/** Value at quantile q (0–1) of a sorted array. */
export function quantile(sorted: Float32Array, q: number): number {
  if (!sorted.length) return NaN;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))));
  return sorted[i];
}
