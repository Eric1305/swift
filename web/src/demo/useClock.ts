import { useCallback, useEffect, useRef, useState } from 'react';

export type Speed = 1 | 5 | 20;
export const SPEEDS: Speed[] = [1, 5, 20];

/** Replay minutes advanced per real second at 1×. At 20× a 180-minute replay takes 36 s. */
export const MINUTES_PER_SECOND_AT_1X = 0.25;

export interface Clock {
  t: number;
  playing: boolean;
  speed: Speed;
  endMin: number;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  setSpeed: (s: Speed) => void;
  seek: (t: number) => void;
}

export function useClock(endMin: number): Clock {
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const speedRef = useRef(speed);
  speedRef.current = speed;

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setT((prev) => {
        const next = prev + dt * MINUTES_PER_SECOND_AT_1X * speedRef.current;
        if (next >= endMin) {
          setPlaying(false);
          return endMin;
        }
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, endMin]);

  const seek = useCallback((v: number) => setT(Math.min(endMin, Math.max(0, v))), [endMin]);
  const play = useCallback(() => setPlaying(true), []);
  const pause = useCallback(() => setPlaying(false), []);
  const toggle = useCallback(() => setPlaying((p) => !p), []);

  return { t, playing, speed, endMin, play, pause, toggle, setSpeed, seek };
}
