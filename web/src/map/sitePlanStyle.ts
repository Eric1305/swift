import type { Map as MapLibreMap } from 'maplibre-gl';

/** Light basemap (no key). Recolored at load into the Figma "site plan" look. */
export const BASEMAP_URL = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

/** Our white 3D context buildings; the flood is drawn just below this layer. */
export const CONTEXT_BUILDINGS_LAYER = 'swift-context-buildings';

export const SITE = {
  land: '#EEE7DB',
  road: '#8F8A82',
  roadCase: '#837E77',
  park: '#A9D78C',
  water: '#5BBEE2',
  shore: '#EFE4CE',
  context: '#F2F0EC',
  label: '#5F5A52',
} as const;

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
      else if (/water/.test(id)) safe(() => map.setPaintProperty(id, 'fill-color', SITE.water));
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
