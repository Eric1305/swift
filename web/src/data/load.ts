import type { Fixtures, HouseholdRecord } from './types';

const DATA = `${import.meta.env.BASE_URL}data/`;

async function getJson<T>(file: string): Promise<T> {
  const res = await fetch(DATA + file);
  if (!res.ok) throw new Error(`${file}: HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export function dataUrl(file: string): string {
  return DATA + file;
}

/** Loads every fixture the dashboard needs up front (records are fetched lazily). */
export async function loadFixtures(): Promise<Fixtures> {
  const [meta, hh, timeline, queue, routes, dk, briefings, imagery, results, liveFallback, gpuSample] =
    await Promise.all([
      getJson<Fixtures['meta']>('meta.json'),
      getJson<{ features: Fixtures['households'] }>('households.geojson'),
      getJson<Fixtures['timeline']>('timeline.json'),
      getJson<Fixtures['queue']>('queue.json'),
      getJson<Fixtures['routes']>('routes.json'),
      getJson<{ features: Fixtures['doorknock'] }>('doorknock.geojson'),
      getJson<Fixtures['briefings']>('briefings.json'),
      getJson<Fixtures['imagery']>('imagery.json'),
      getJson<Fixtures['results']>('results.json'),
      getJson<Fixtures['liveFallback']>('live_fallback.json'),
      getJson<Fixtures['gpuSample']>('gpu_sample.json'),
    ]);
  const byTime = <T extends { t_min: number }>(a: T[]) => [...a].sort((x, y) => x.t_min - y.t_min);
  return {
    meta,
    households: hh.features,
    timeline: byTime(timeline),
    queue: byTime(queue),
    routes,
    doorknock: dk.features,
    briefings: byTime(briefings),
    imagery,
    results,
    liveFallback,
    gpuSample,
  };
}

const recordCache = new Map<string, Promise<HouseholdRecord | null>>();

export function loadRecord(id: string): Promise<HouseholdRecord | null> {
  let p = recordCache.get(id);
  if (!p) {
    p = getJson<HouseholdRecord>(`records/${id}.json`).catch(() => null);
    recordCache.set(id, p);
  }
  return p;
}
