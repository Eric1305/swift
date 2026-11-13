import * as maplibregl from 'maplibre-gl';
// MapLibre 6 ships its worker as a separate ES module next to the main bundle. Bundling
// moves the main module, which breaks the default relative worker URL, so bundle the worker
// ourselves and point MapLibre at it. The same instance is handed to react-map-gl (mapLib).
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

maplibregl.setWorkerUrl(workerUrl);

export default maplibregl;
