import { useEffect, useState } from 'react';
import { api } from '../data/api';
import type { GpuStats } from '../data/types';

const HISTORY = 30;

export interface GpuState {
  stats: GpuStats;
  history: number[];
  source: 'idle' | 'live' | 'sample';
}

/** Polls /api/gpu every second while `active`; falls back to gpu_sample.json. */
export function useGpu(active: boolean, sample: GpuStats): GpuState {
  const [state, setState] = useState<GpuState>({ stats: sample, history: [], source: 'idle' });

  useEffect(() => {
    if (!active) {
      setState({ stats: sample, history: [], source: 'idle' });
      return;
    }
    let alive = true;
    const poll = async () => {
      let stats: GpuStats;
      let source: GpuState['source'];
      try {
        stats = await api.gpu();
        source = 'live';
      } catch {
        stats = sample;
        source = 'sample';
      }
      if (!alive) return;
      setState((prev) => ({ stats, source, history: [...prev.history, stats.gpu_util].slice(-HISTORY) }));
    };
    void poll();
    const id = setInterval(poll, 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [active, sample]);

  return state;
}
