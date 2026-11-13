import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../data/api';
import type { CallStatus, HouseholdRecord, LiveFallback, TranscriptLine } from '../data/types';

const POLL_MS = 2000;
const GIVE_UP_MS = 90_000;

export interface LiveCall {
  phase: 'idle' | 'running' | 'done';
  callStatus: CallStatus;
  source: 'api' | 'fallback';
  transcript: TranscriptLine[];
  record: HouseholdRecord | null;
  startedAt: number | null;
}

const IDLE: LiveCall = { phase: 'idle', callStatus: 'idle', source: 'api', transcript: [], record: null, startedAt: null };

/**
 * Scene 6: call DEMO_PHONE through the agent server and stream the record.
 * Falls back to live_fallback.json if the API fails or 90 s pass without a result.
 * The returned promise resolves when the call is finished either way.
 */
export function useLiveCall(fallback: LiveFallback) {
  const [state, setState] = useState<LiveCall>(IDLE);
  const cancelRef = useRef<() => void>(() => {});

  useEffect(() => () => cancelRef.current(), []);

  const reset = useCallback(() => {
    cancelRef.current();
    setState(IDLE);
  }, []);

  const start = useCallback((): Promise<void> => {
    cancelRef.current();
    let cancelled = false;
    const timers: ReturnType<typeof setTimeout>[] = [];
    cancelRef.current = () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
    const wait = (ms: number) => new Promise<void>((r) => timers.push(setTimeout(r, ms)));
    const startedAt = Date.now();
    setState({ ...IDLE, phase: 'running', callStatus: 'ringing', startedAt });

    const playFallback = async () => {
      setState((s) => ({ ...s, source: 'fallback', callStatus: 'in-progress', transcript: [] }));
      for (const step of fallback.steps) {
        await wait(step.delay_ms);
        if (cancelled) return;
        setState((s) => ({ ...s, transcript: [...s.transcript, { who: step.who, text: step.text }] }));
      }
      if (cancelled) return;
      setState((s) => ({ ...s, phase: 'done', callStatus: 'completed', record: fallback.record }));
    };

    const run = async () => {
      try {
        await api.demoCall();
      } catch {
        return playFallback();
      }
      let failures = 0;
      while (!cancelled && Date.now() - startedAt < GIVE_UP_MS) {
        await wait(POLL_MS);
        if (cancelled) return;
        try {
          const live = await api.live();
          failures = 0;
          const done = live.call_status === 'completed' || live.call_status === 'no-answer';
          setState((s) => ({
            ...s,
            callStatus: live.call_status,
            transcript: live.record?.transcript ?? s.transcript,
            record: live.record ?? s.record,
            phase: done ? 'done' : 'running',
          }));
          if (done) return;
        } catch {
          failures += 1;
          if (failures >= 3) return playFallback();
        }
      }
      if (!cancelled) return playFallback();
    };

    return run();
  }, [fallback]);

  return { live: state, start, reset };
}
