import type { Map as MapLibreMap } from 'maplibre-gl';

/** Light basemap (no key). Recolored at load into the Figma "site plan" look. */
export const BASEMAP_URL = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

/** Our white 3D context buildings; the flood is drawn just below this layer. */
export const CONTEXT_BUILDINGS_LAYER = 'swift-context-buildings';

/** Default "ink" style: monochrome paper map so only the water (halftone blue) and status colors carry color.
 *  `?style=color` restores the original site-plan palette. */
export const INK = new URLSearchParams(window.location.search).get('style') !== 'color';

const COLOR_SITE = {
  land: '#EEE7DB',
  road: '#8F8A82',
  roadCase: '#837E77',
  park: '#A9D78C',
  water: '#5BBEE2',
  waterDeep: '#2375CF',
  shore: '#EFE4CE',
  context: '#F2F0EC',
  label: '#5F5A52',
};
const INK_SITE: typeof COLOR_SITE = {
  land: '#F3F2EF',
  road: '#B4B1AB',
  roadCase: '#A29F99',
  park: '#E3E2DD',
  water: '#CBD0D8',
  waterDeep: '#8E98A8',
  shore: '#ECEBE7',
  context: '#FFFFFF',
  label: '#76726B',
};
export const SITE = INK ? INK_SITE : COLOR_SITE;

function safe(fn: () => void) {
  try {
    fn();
  } catch {
    /* layer lacks this property: ignore */
  }
}

/**
 * Recolors CARTO Positron to the site-plan palette (cream land, taupe roads, cyan water,
 * green parks) and swaps flat building footprints for white extrusions.
 * Matches layers by id pattern, so it tolerates small upstream style changes.
 */
export function applySitePlanStyle(map: MapLibreMap) {
  const style = map.getStyle();
  let buildingSource: { source: string; sourceLayer: string } | null = null;
  const waterways: { id: string; source: string; sourceLayer: string }[] = [];
  let waterFill: { id: string; source: string; sourceLayer: string } | null = null;
  const srcOf = (layer: (typeof style.layers)[number]) =>
    'source' in layer && 'source-layer' in layer && layer['source-layer']
      ? { source: layer.source as string, sourceLayer: layer['source-layer'] as string }
      : null;

  for (const layer of style.layers) {
    const id = layer.id;
    const type = layer.type;
    if (type === 'background') {
      safe(() => map.setPaintProperty(id, 'background-color', SITE.land));
      continue;
    }
    if (/building/.test(id)) {
      if (!buildingSource && 'source' in layer && 'source-layer' in layer && layer['source-layer']) {
        buildingSource = { source: layer.source as string, sourceLayer: layer['source-layer'] as string };
      }
      map.setLayoutProperty(id, 'visibility', 'none');
      continue;
    }
    if (/rail|aeroway|boundary|poi/.test(id)) {
      map.setLayoutProperty(id, 'visibility', 'none');
      continue;
    }
    if (type === 'fill') {
      if (/water_shadow/.test(id)) safe(() => map.setPaintProperty(id, 'fill-color', SITE.shore));
      else if (/water/.test(id)) {
        safe(() => map.setPaintProperty(id, 'fill-color', SITE.water));
        safe(() => map.setPaintProperty(id, 'fill-antialias', true));
        const src = srcOf(layer);
        if (src && !waterFill) waterFill = { id, ...src };
      }
      else if (/park|wood|grass|landcover|green|cemetery/.test(id)) {
        safe(() => map.setPaintProperty(id, 'fill-color', SITE.park));
        safe(() => map.setPaintProperty(id, 'fill-opacity', 0.9));
      } else safe(() => map.setPaintProperty(id, 'fill-color', SITE.land));
      continue;
    }
    if (type === 'line') {
      if (/waterway/.test(id)) {
        // Bear Creek / Langham Creek / bayous: wider, brighter channels so the real drainage reads.
        safe(() => map.setPaintProperty(id, 'line-color', SITE.water));
        safe(() => map.setPaintProperty(id, 'line-width', ['interpolate', ['exponential', 1.6], ['zoom'], 10, 1, 13, 2.5, 15, 6, 17, 14]));
        safe(() => map.setPaintProperty(id, 'line-opacity', 1));
        const src = srcOf(layer);
        if (src) waterways.push({ id, ...src });
      }
      else if (/road|tunnel|bridge|highway|street|motorway|path/.test(id)) {
        safe(() => map.setPaintProperty(id, 'line-color', /case|casing/.test(id) ? SITE.roadCase : SITE.road));
      }
      continue;
    }
    if (type === 'symbol') {
      safe(() => map.setPaintProperty(id, 'text-color', /water/.test(id) ? '#FFFFFF' : SITE.label));
      safe(() => map.setPaintProperty(id, 'text-halo-color', /water/.test(id) ? SITE.water : SITE.land));
    }
  }

  // Defined water edges (cartographic shoreline): a white casing under every creek line and a
  // crisp white outline + inner deep-blue rim around ponds / the reservoir.
  // zoom must be the top-level input, so the casing gets its own (wider) curve
  const casingWidth = ['interpolate', ['exponential', 1.6], ['zoom'], 10, 3, 13, 5, 15, 8.5, 17, 17];
  for (const w of waterways) {
    const casing = `swift-casing-${w.id}`;
    if (map.getLayer(casing)) continue;
    map.addLayer(
      {
        id: casing,
        type: 'line',
        source: w.source,
        'source-layer': w.sourceLayer,
        filter: map.getFilter(w.id) ?? undefined,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#FFFFFF', 'line-width': casingWidth as never, 'line-opacity': 0.95 },
      },
      w.id,
    );
    safe(() => map.setLayoutProperty(w.id, 'line-cap', 'round'));
    safe(() => map.setLayoutProperty(w.id, 'line-join', 'round'));
  }
  if (waterFill && !map.getLayer('swift-water-rim')) {
    const wf = waterFill as { id: string; source: string; sourceLayer: string };
    const base = { source: wf.source, 'source-layer': wf.sourceLayer, filter: map.getFilter(wf.id) ?? undefined };
    // Directly above the water fill, so anything the style draws over water (parks, dry
    // detention basins under landuse) also hides the outline: edges only where water shows.
    const idx = style.layers.findIndex((l) => l.id === wf.id);
    const above = style.layers[idx + 1]?.id;
    map.addLayer({ id: 'swift-water-rim', type: 'line', ...base, paint: { 'line-color': SITE.waterDeep, 'line-width': 3, 'line-offset': 1.5, 'line-opacity': 0.55 } }, above);
    map.addLayer({ id: 'swift-water-shore', type: 'line', ...base, paint: { 'line-color': '#FFFFFF', 'line-width': 1.6 } }, above);
  }

  if (buildingSource && !map.getLayer(CONTEXT_BUILDINGS_LAYER)) {
    map.addLayer({
      id: CONTEXT_BUILDINGS_LAYER,
      type: 'fill-extrusion',
      source: buildingSource.source,
      'source-layer': buildingSource.sourceLayer,
      minzoom: 13,
      paint: {
        'fill-extrusion-color': SITE.context,
        'fill-extrusion-height': ['coalesce', ['get', 'render_height'], ['get', 'height'], 6],
        'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
        'fill-extrusion-opacity': 0.95,
        'fill-extrusion-vertical-gradient': true,
      },
    });
  }
  map.setLight({ anchor: 'viewport', color: '#ffffff', intensity: 0.4, position: [1.4, 210, 40] });
}
