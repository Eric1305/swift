import type { Briefing } from '../data/types';
import type { GpuState } from '../demo/useGpu';
import { formatT } from '../demo/timeline';
import cx from './cx';

const W = 150;
const H = 40;

function Sparkline({ values, max }: { values: number[]; max: number }) {
  if (values.length < 2) return <svg width={W} height={H} className="sparkline" aria-hidden />;
  const step = W / (values.length - 1);
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)} ${(H - 2 - (Math.min(max, v) / max) * (H - 4)).toFixed(1)}`).join(' ');
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="sparkline" aria-hidden>
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Model panel. The model is hosted on the organizers' GB10 server, so /api/gpu reports LLM load
 * (calls in flight, total calls, latency); the GPU fields are usually 0 and are not shown.
 */
export default function Gb10Panel({ gpu, shifted, briefing }: { gpu: GpuState; shifted: boolean; briefing?: Briefing | null | false }) {
  const { stats, history, source } = gpu;
  const idle = source === 'idle';
  const peak = Math.max(4, ...history);
  return (
    <aside className={cx('panel', 'gb10', shifted && 'is-shifted')} aria-label="Model status">
      <div className="row-between">
        <span className="gb10__title">
          <strong>Qwen3-VL</strong> <span>on GB10</span>
        </span>
        <span className="gb10__live">
          <i className={cx(idle ? 'is-idle' : source === 'sample' ? 'is-sample' : 'is-live')} />
          {idle ? 'idle · /api/gpu' : source === 'live' ? 'live · 1 s' : 'sample · offline'}
        </span>
      </div>
      <div className="gb10__gpu">
        <div>
          <span className="micro">Calls in flight</span>
          <strong>{idle ? 0 : stats.llm_running}</strong>
        </div>
        <Sparkline values={history} max={peak} />
      </div>
      <div className="gb10__stats">
        <div className="stat stat--grow">
          <span>Total calls</span>
          <strong className={cx(!idle && stats.llm_running > 0 && 'is-accent')}>{idle ? '—' : (stats.llm_calls ?? 0).toLocaleString()}</strong>
        </div>
        <div className="stat stat--grow">
          <span>Latency</span>
          <strong>{idle || !stats.latency_ms ? '—' : `${Math.round(stats.latency_ms)} ms`}</strong>
        </div>
      </div>
      {briefing !== undefined && briefing !== false && (
        <div className="gb10__brief">
          <span className="micro">Briefing{briefing ? ` · ${formatT(briefing.t_min)}` : ''} · by Qwen</span>
          <p>{briefing ? briefing.text : 'The first briefing appears once calls start.'}</p>
        </div>
      )}
    </aside>
  );
}
