import type { GpuState } from '../demo/useGpu';
import cx from './cx';

const W = 150;
const H = 40;

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <svg width={W} height={H} className="sparkline" aria-hidden />;
  const step = W / (values.length - 1);
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)} ${(H - 2 - (Math.min(100, v) / 100) * (H - 4)).toFixed(1)}`).join(' ');
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="sparkline" aria-hidden>
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" />
    </svg>
  );
}

export default function Gb10Panel({ gpu, shifted }: { gpu: GpuState; shifted: boolean }) {
  const { stats, history, source } = gpu;
  const idle = source === 'idle';
  const memPct = stats.mem_total_gb ? (stats.mem_used_gb / stats.mem_total_gb) * 100 : 0;
  return (
    <aside className={cx('panel', 'gb10', shifted && 'is-shifted')} aria-label="GB10 status">
      <div className="row-between">
        <span className="gb10__title">
          <strong>GB10</strong> <span>DGX Spark</span>
        </span>
        <span className="gb10__live">
          <i className={cx(idle ? 'is-idle' : source === 'sample' ? 'is-sample' : 'is-live')} />
          {idle ? 'idle · /api/gpu' : source === 'live' ? 'live · 1 s' : 'sample · offline'}
        </span>
      </div>
      <div className="gb10__gpu">
        <div>
          <span className="micro">GPU</span>
          <strong>{idle ? '—' : `${Math.round(stats.gpu_util)}%`}</strong>
        </div>
        <Sparkline values={history} />
      </div>
      <div className="gb10__mem">
        <div className="row-between">
          <span className="micro">Memory</span>
          <span className="mono-strong">
            {stats.mem_used_gb.toFixed(1)} / {Math.round(stats.mem_total_gb)} GB
          </span>
        </div>
        <div className="meter">
          <i style={{ width: `${idle ? 0 : memPct}%` }} />
        </div>
      </div>
      <div className="gb10__stats">
        <div className="stat stat--grow">
          <span>LLM calls in flight</span>
          <strong className={cx(!idle && stats.llm_running > 0 && 'is-accent')}>{idle ? 0 : stats.llm_running}</strong>
        </div>
        <div className="stat">
          <span>Temp</span>
          <strong>{Math.round(stats.temp_c)}°C</strong>
        </div>
      </div>
    </aside>
  );
}
