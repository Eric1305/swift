import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from 'react';
import { AmbientLight, DirectionalLight, LightingEffect, type LayersList } from '@deck.gl/core';
import { ArcLayer, BitmapLayer, PathLayer, PolygonLayer } from '@deck.gl/layers';
import { TileLayer, TripsLayer, type _TileLoadProps as TileLoadProps } from '@deck.gl/geo-layers';
import { PathStyleExtension, type PathStyleExtensionProps } from '@deck.gl/extensions';
import { MapboxOverlay, type MapboxOverlayProps } from '@deck.gl/mapbox';
import { Map as BaseMap, Marker, useMap, type MapRef } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import maplibregl from './maplibreWorker';
import type { DisplayStatus, DoorknockFeature, Fixtures, HouseholdFeature, LonLat, Route } from '../data/types';
import { dataUrl } from '../data/load';
import { applySitePlanStyle, BASEMAP_URL, CONTEXT_BUILDINGS_LAYER } from './sitePlanStyle';
import { INK, NAVY, ROOF, VEHICLE } from './colors';
import { decodeTile, FloodBitmapLayer, quantile, TERRARIUM_URL, type StudyArea, type TerrainTile } from './floodLayer';
import { ImageryPin, ImageryPopup } from '../components/Imagery';
import cx from '../components/cx';

export interface MapHandle {
  flyIn: () => void;
  flyTo: (id: string) => void;
  zoomBy: (delta: number) => void;
  resetNorth: () => void;
}

interface Props {
  ref?: Ref<MapHandle>;
  fx: Fixtures;
  t: number;
  statuses: Map<string, DisplayStatus>;
  selectedId: string | null;
  liveId: string | null;
  imageryId: string | null;
  onSelect: (id: string) => void;
  onImagery: (id: string | null) => void;
}

/**
 * Water level schedule, as elevation quantiles of the study area: at t=0 only the creek
 * channel (lowest ~3 %) is wet; by the end of the replay ~40 % of the area is under water.
 * Ease-out so most of the rise happens early, like a flash flood.
 */
const FLOOD_Q_START = 0.03;
const FLOOD_Q_END = 0.4;
/** 'terrain' = flood from real elevation tiles; 'pipeline' = depth_*.png from the pipeline. */
/** Override with `?flood=pipeline` (offline / venue firewall: no S3 terrain tiles needed). */
const FLOOD_SOURCE: 'terrain' | 'pipeline' =
  new URLSearchParams(window.location.search).get('flood') === 'pipeline' ? 'pipeline' : 'terrain';
const PIPELINE_DEPTH_OPACITY = 0.55;

/** Interleaved-mode prop (@deck.gl/mapbox): insert the layer below this MapLibre layer. */
type BeforeId = { beforeId?: string };

const centroid = (f: { geometry: { coordinates: LonLat[][] } }): LonLat => {
  const ring = f.geometry.coordinates[0].slice(0, -1);
  const [x, y] = ring.reduce(([a, b], [c, d]) => [a + c, b + d], [0, 0]);
  return [x / ring.length, y / ring.length];
};

const lighting = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 255, 255], intensity: 1.1 }),
  sun: new DirectionalLight({ color: [255, 250, 240], intensity: 1.4, direction: [-1.2, -0.6, -2] }),
});

const dash = new PathStyleExtension({ dash: true });

/**
 * deck.gl drawn inside MapLibre's own WebGL context: markers stay on top, 3D depth is shared.
 * Created once per map. Removal is deferred a tick so React StrictMode's mount → unmount →
 * mount doesn't attach two luma.gl devices to the same GL context (luma throws on that).
 */
function DeckOverlay(props: MapboxOverlayProps) {
  const { current: mapRef } = useMap();
  const overlay = useRef<MapboxOverlay | null>(null);
  const removal = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const map = mapRef?.getMap();
    if (!map) return;
    if (removal.current) clearTimeout(removal.current);
    if (!overlay.current) {
      // Compatibility shim: deck.gl 9.4's interleaved mode reads `map.transform`, which
      // MapLibre 6 moved to `map._camera.transform`. Remove once @deck.gl/mapbox supports v6.
      if (!('transform' in map)) {
        Object.defineProperty(map, 'transform', {
          configurable: true,
          get: () => (map as unknown as { _camera: { transform: unknown } })._camera.transform,
        });
      }
      overlay.current = new MapboxOverlay({ ...props, interleaved: true });
      map.addControl(overlay.current as unknown as maplibregl.IControl);
    }
    return () => {
      removal.current = setTimeout(() => {
        if (overlay.current) map.removeControl(overlay.current as unknown as maplibregl.IControl);
        overlay.current = null;
      }, 0);
    };
    // props are pushed by the effect below; creation depends on the map only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapRef]);

  useEffect(() => {
    overlay.current?.setProps(props);
  });
  return null;
}

/** Elevation samples collected from loaded terrain tiles (inside the study area only). */
function useElevationStats() {
  const tiles = useRef(new Map<string, Float32Array>());
  const [sorted, setSorted] = useState<Float32Array>(new Float32Array());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const add = useCallback((key: string, samples: Float32Array) => {
    if (tiles.current.has(key) || samples.length === 0) return;
    tiles.current.set(key, samples);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const all = new Float32Array([...tiles.current.values()].reduce((n, a) => n + a.length, 0));
      let o = 0;
      for (const a of tiles.current.values()) {
        all.set(a, o);
        o += a.length;
      }
      setSorted(all.sort());
    }, 150);
  }, []);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  return { sorted, add };
}

export default function SwiftMap({ ref, fx, t, statuses, selectedId, liveId, imageryId, onSelect, onImagery }: Props) {
  const { meta } = fx;
  const mapRef = useRef<MapRef>(null);
  const [styleReady, setStyleReady] = useState(false);
  const [terrainFailed, setTerrainFailed] = useState(false);
  const elevation = useElevationStats();

  const home = useMemo(
    () => ({ center: meta.center as [number, number], zoom: meta.zoom, pitch: meta.pitch, bearing: meta.bearing }),
    [meta],
  );
  const centers = useMemo(() => new Map(fx.households.map((f) => [f.properties.id, centroid(f)])), [fx.households]);

  // Study area = the pipeline's depth bounds, slightly padded; the flood feathers out at its edge.
  const area = useMemo<StudyArea>(() => {
    const [[w, s], [e, n]] = meta.depth_stages[0]?.bounds ?? [[meta.center[0] - 0.03, meta.center[1] - 0.02], [meta.center[0] + 0.03, meta.center[1] + 0.02]];
    const px = (e - w) * 0.08;
    const py = (n - s) * 0.08;
    return { west: w - px, south: s - py, east: e + px, north: n + py, feather: 0.12 };
  }, [meta]);

  useImperativeHandle(ref, () => ({
    flyIn: () => {
      const map = mapRef.current;
      if (!map) return;
      map.jumpTo({ ...home, zoom: home.zoom - 3, pitch: 0, bearing: 0 });
      map.flyTo({ ...home, duration: 4000, essential: true });
    },
    flyTo: (id) => {
      const c = centers.get(id);
      const map = mapRef.current;
      if (c && map) map.flyTo({ center: c, zoom: Math.max(map.getZoom(), home.zoom + 1.2), duration: 1600, essential: true });
    },
    zoomBy: (d) => {
      const map = mapRef.current;
      if (map) map.easeTo({ zoom: map.getZoom() + d, duration: 300 });
    },
    resetNorth: () => mapRef.current?.easeTo({ bearing: home.bearing, pitch: home.pitch, duration: 600 }),
  }), [centers, home]);

  const progress = meta.timeline.end_min ? Math.min(1, Math.max(0, t / meta.timeline.end_min)) : 0;
  const level = useMemo(() => {
    if (!elevation.sorted.length) return NaN;
    const q = FLOOD_Q_START + (FLOOD_Q_END - FLOOD_Q_START) * (1 - (1 - progress) ** 2);
    return quantile(elevation.sorted, q);
  }, [elevation.sorted, progress]);
  const floor = useMemo(() => quantile(elevation.sorted, 0.005), [elevation.sorted]);

  const addSamples = elevation.add;
  const getTileData = useCallback(
    async ({ url, bbox, signal, index }: TileLoadProps): Promise<TerrainTile | null> => {
      if (!url || !('west' in bbox)) return null;
      const out = await decodeTile(url, bbox, area, signal);
      if (out) addSamples(`${index.z}/${index.x}/${index.y}`, out.samples);
      return out;
    },
    [area, addSamples],
  );

  const layers = useMemo(() => {
    const status = (id: string): DisplayStatus => statuses.get(id) ?? 'not_called';
    const knock = fx.doorknock.filter((d) => d.properties.t_min <= t);
    const activeRoutes = fx.routes.filter((r) => r.timestamps[0] <= t);
    const calling = fx.households.filter((h) => status(h.properties.id) === 'calling');

    // Flood: real terrain unless it failed to load, then the pipeline's depth PNGs.
    const useTerrain = FLOOD_SOURCE === 'terrain' && !terrainFailed;
    let flood: LayersList = [];
    if (useTerrain) {
      // Until the first tiles report elevations, level is -inf (tiles load, nothing floods).
      const lvl = Number.isFinite(level) ? level : -1e9;
      const maxDepth = Number.isFinite(level) ? Math.max(0.5, level - floor) : 1;
      flood = [
        new TileLayer<TerrainTile | null, BeforeId>({
          id: 'flood-terrain',
          data: TERRARIUM_URL,
          minZoom: 11,
          maxZoom: 14,
          tileSize: 256,
          extent: [area.west, area.south, area.east, area.north],
          maxRequests: 8,
          beforeId: CONTEXT_BUILDINGS_LAYER,
          getTileData,
          onTileError: () => setTerrainFailed(true),
          updateTriggers: { renderSubLayers: [lvl, maxDepth] },
          renderSubLayers: (props) => {
            const { tile, data } = props;
            if (!data || !('west' in tile.bbox)) return null;
            const { west, south, east, north } = tile.bbox;
            return new FloodBitmapLayer({
              id: props.id,
              image: data.image,
              bounds: [west, south, east, north],
              level: lvl,
              base: data.base,
              range: data.range,
              maxDepth,
              textureParameters: { minFilter: 'linear', magFilter: 'linear' },
            });
          },
        }),
      ];
    } else {
      const stages = meta.depth_stages;
      let i = 0;
      while (i < stages.length - 1 && stages[i + 1].t_min <= t) i++;
      const a = stages[i];
      const b = stages[i + 1];
      const f = b ? Math.min(1, Math.max(0, (t - a.t_min) / (b.t_min - a.t_min))) : 0;
      flood = [a, b].filter(Boolean).map((s, k) =>
        new BitmapLayer<BeforeId>({
          id: `depth-${k}`,
          image: dataUrl(s.png),
          bounds: [s.bounds[0][0], s.bounds[0][1], s.bounds[1][0], s.bounds[1][1]],
          opacity: PIPELINE_DEPTH_OPACITY * (k === 0 ? 1 - f : f),
          beforeId: CONTEXT_BUILDINGS_LAYER,
        }),
      );
    }

    // The open imagery item's real georeferenced Harvey aerial, draped at its bounds.
    const aerials: LayersList = fx.imagery
      .filter((img) => img.image_id === imageryId)
      .map((img) =>
        new BitmapLayer<BeforeId>({
          id: `aerial-${img.image_id}`,
          image: dataUrl(img.thumb),
          bounds: [img.bounds[0][0], img.bounds[0][1], img.bounds[1][0], img.bounds[1][1]],
          opacity: 0.92,
          beforeId: CONTEXT_BUILDINGS_LAYER,
        }),
      );

    return [
      ...flood,
      ...aerials,
      new PolygonLayer<DoorknockFeature>({
        id: 'doorknock-fill',
        data: knock,
        getPolygon: (d) => d.geometry.coordinates,
        filled: true,
        stroked: false,
        getFillColor: [INK[0], INK[1], INK[2], 14],
      }),
      new PathLayer<DoorknockFeature, PathStyleExtensionProps<DoorknockFeature>>({
        id: 'doorknock-outline',
        data: knock,
        getPath: (d) => d.geometry.coordinates[0],
        getColor: INK,
        widthMinPixels: 1.5,
        getDashArray: [6, 4],
        dashJustified: true,
        extensions: [dash],
      }),
      new PolygonLayer<HouseholdFeature>({
        id: 'households',
        data: fx.households,
        getPolygon: (d) => d.geometry.coordinates,
        extruded: true,
        wireframe: true,
        // +1.5 m so the status roof sits above the matching basemap building
        getElevation: (d) => d.properties.height_m + 1.5,
        getFillColor: (d) => ROOF[status(d.properties.id)],
        getLineColor: (d) => (status(d.properties.id) === 'no_answer' ? [255, 255, 255, 255] : [0, 0, 0, 30]),
        material: { ambient: 0.55, diffuse: 0.6, shininess: 8, specularColor: [255, 255, 255] },
        pickable: true,
        autoHighlight: true,
        highlightColor: [0, 78, 120, 90],
        onClick: ({ object }) => object && onSelect(object.properties.id),
        updateTriggers: { getFillColor: statuses, getLineColor: statuses },
      }),
      new PathLayer<Route, PathStyleExtensionProps<Route>>({
        id: 'route-plan',
        data: activeRoutes,
        getPath: (d) => d.path,
        getColor: [INK[0], INK[1], INK[2], 110],
        widthMinPixels: 1.5,
        getDashArray: [3, 4],
        extensions: [dash],
      }),
      new TripsLayer<Route>({
        id: 'trips',
        data: fx.routes,
        getPath: (d) => d.path,
        getTimestamps: (d) => d.timestamps,
        getColor: (d) => VEHICLE[d.vehicle],
        currentTime: t,
        trailLength: 20,
        widthMinPixels: 4,
        capRounded: true,
        jointRounded: true,
      }),
      new ArcLayer<HouseholdFeature>({
        id: 'call-arcs',
        data: calling,
        getSourcePosition: () => meta.hub,
        getTargetPosition: (d) => centers.get(d.properties.id) ?? meta.hub,
        getSourceColor: [NAVY[0], NAVY[1], NAVY[2], 140],
        getTargetColor: [56, 189, 248, 230],
        getWidth: 1.6 + Math.sin(t * 6) * 0.6,
        getHeight: 0.6,
        updateTriggers: { getWidth: t },
      }),
    ];
  }, [fx, meta, t, statuses, centers, onSelect, area, getTileData, terrainFailed, level, floor, imageryId]);

  const knockLabels = fx.doorknock.filter((d) => d.properties.t_min <= t);
  const selected = selectedId ? centers.get(selectedId) : undefined;
  const live = liveId ? centers.get(liveId) : undefined;

  return (
    <BaseMap
      ref={mapRef}
      mapLib={maplibregl}
      mapStyle={BASEMAP_URL}
      initialViewState={{ longitude: home.center[0], latitude: home.center[1], zoom: home.zoom, pitch: home.pitch, bearing: home.bearing }}
      maxPitch={70}
      attributionControl={false}
      onLoad={(e) => {
        applySitePlanStyle(e.target);
        setStyleReady(true);
      }}
      style={{ width: '100%', height: '100%' }}
    >
      {styleReady && <DeckOverlay layers={layers} effects={[lighting]} getCursor={({ isHovering }) => (isHovering ? 'pointer' : 'grab')} />}
      <Marker longitude={meta.hub[0]} latitude={meta.hub[1]} anchor="left">
        <span className="map-pill map-pill--navy">● Call hub</span>
      </Marker>
      <Marker longitude={meta.staging[0]} latitude={meta.staging[1]} anchor="center">
        <span className="map-pill map-pill--terracotta">Staging</span>
      </Marker>
      {knockLabels.map((d, k) => {
        const ring = d.geometry.coordinates[0];
        const top = ring.reduce((m, p) => (p[1] > m[1] ? p : m), ring[0]);
        return (
          <Marker key={k} longitude={top[0]} latitude={top[1]} anchor="bottom-left">
            <span className="map-pill map-pill--ink">Door-knock · {d.properties.household_ids.length}</span>
          </Marker>
        );
      })}
      {fx.imagery.map((img) => (
        <Marker key={img.image_id} longitude={img.lon} latitude={img.lat} anchor="center">
          <ImageryPin item={img} active={img.image_id === imageryId} onClick={() => onImagery(img.image_id === imageryId ? null : img.image_id)} />
        </Marker>
      ))}
      {fx.imagery.filter((i) => i.image_id === imageryId).map((img) => (
        <Marker key={`pop-${img.image_id}`} longitude={img.lon} latitude={img.lat} anchor="right" offset={[-24, 0]}>
          <ImageryPopup item={img} onClose={() => onImagery(null)} />
        </Marker>
      ))}
      {selected && (
        <Marker longitude={selected[0]} latitude={selected[1]} anchor="center">
          <span className="map-ring" aria-hidden />
        </Marker>
      )}
      {live && (
        <Marker longitude={live[0]} latitude={live[1]} anchor="center">
          <span className={cx('map-ring', 'map-ring--live')} aria-hidden />
        </Marker>
      )}
    </BaseMap>
  );
}
