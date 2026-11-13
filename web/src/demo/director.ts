import type { Speed } from './useClock';

/** Everything the Run Demo script is allowed to drive. */
export interface DirectorContext {
  setScene: (n: number) => void;
  flyIn: () => void;
  resetView: () => void;
  seek: (t: number) => void;
  play: (speed: Speed) => void;
  pause: () => void;
  startGpu: () => void;
  openTopRanked: () => void;
  openImagery: () => void;
  closeOverlays: () => void;
  startLiveCall: () => Promise<void>;
  showResults: () => void;
}

export const SCENE_COUNT = 7;

/**
 * The fixed scene list from PLAN.md (T4). Times are seconds from pressing Run Demo.
 * Resolves when the demo ends; rejects with AbortError when stopped.
 */
export async function runDemo(ctx: DirectorContext, signal: AbortSignal): Promise<void> {
  const t0 = performance.now();
  const at = (seconds: number) =>
    new Promise<void>((resolve, reject) => {
      const ms = Math.max(0, t0 + seconds * 1000 - performance.now());
      const id = setTimeout(resolve, ms);
      signal.addEventListener('abort', () => {
        clearTimeout(id);
        reject(new DOMException('stopped', 'AbortError'));
      }, { once: true });
    });
  const check = () => {
    if (signal.aborted) throw new DOMException('stopped', 'AbortError');
  };

  // 1 · 0 s: fly in from a high view, water at stage 0
  ctx.setScene(1);
  ctx.closeOverlays();
  ctx.pause();
  ctx.seek(0);
  ctx.flyIn();

  // 2 · 5 s: play at 20×, arcs fan out, GB10 load starts
  await at(5);
  ctx.setScene(2);
  ctx.startGpu();
  ctx.play(20);

  // 3 · 25 s: pause and open the top-ranked red house
  await at(25);
  ctx.setScene(3);
  ctx.pause();
  ctx.openTopRanked();

  // 4 · 35 s: resume — trips, door-knock clusters, briefing updates
  await at(35);
  ctx.setScene(4);
  ctx.play(20);

  // 5 · 55 s: imagery pins with one popup open
  await at(55);
  ctx.setScene(5);
  ctx.openImagery();

  // 6 · 65 s: the live phone call (API, or live_fallback.json)
  await at(65);
  ctx.setScene(6);
  ctx.pause();
  ctx.closeOverlays();
  await ctx.startLiveCall();
  check();

  // 7 · end: results card
  await at(Math.max(0, (performance.now() - t0) / 1000 + 2));
  ctx.setScene(7);
  ctx.showResults();
}
