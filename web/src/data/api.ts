import type { GpuStats, LiveResponse } from './types';

// Same origin when served from the GB10; VITE_API_URL points at the tunnel in dev.
// Any failure is reported to the caller, which falls back to fixtures.
const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');

async function call<T>(method: 'GET' | 'POST', path: string, timeoutMs = 4000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, { method, signal: ctrl.signal });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    const type = res.headers.get('content-type') ?? '';
    if (!type.includes('json')) throw new Error(`${path}: not JSON`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  demoCall: () => call<{ call_id: string }>('POST', '/api/demo-call', 8000),
  live: () => call<LiveResponse>('GET', '/api/live'),
  gpu: () => call<GpuStats>('GET', '/api/gpu', 1500),
  simulateLive: () => call<{ started: boolean }>('POST', '/api/simulate-live'),
};
