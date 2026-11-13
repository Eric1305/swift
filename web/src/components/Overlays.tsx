import type { Results } from '../data/types';
import type { LiveCall } from '../demo/useLiveCall';
import { IconButton } from './ui';
import cx from './cx';
import plusIcon from '../assets/icons/plus.svg';
import minusIcon from '../assets/icons/minus.svg';
import compassIcon from '../assets/icons/compass.svg';

export function Legend({ narrow }: { narrow: boolean }) {
  return (
    <div className={cx('legend', narrow && 'is-narrow')} aria-label="Water depth scale">
      <div className="legend__depth">
        <span>Water depth&nbsp;&nbsp;0 → 6 ft</span>
        <i />
      </div>
    </div>
  );
}

export function MapControls({ onZoomIn, onZoomOut, onNorth }: { onZoomIn: () => void; onZoomOut: () => void; onNorth: () => void }) {
  return (
    <div className="map-controls">
      <IconButton icon={plusIcon} label="Zoom in" onClick={onZoomIn} />
      <IconButton icon={minusIcon} label="Zoom out" onClick={onZoomOut} />
      <IconButton icon={compassIcon} label="Reset north" onClick={onNorth} />
    </div>
  );
}

export function SheetTag({ scene, live }: { scene: number; live: boolean }) {
  return (
    <div className="sheet-tag" aria-hidden>
      <div className="sheet-tag__row">
        <span>SHEET {String(Math.max(scene, 1)).padStart(2, '0')} · BEAR CREEK · 1:5000</span>
        <span className="sheet-tag__site">{live ? '● LIVE' : '● SITE'}</span>
      </div>
      <i className="sheet-tag__scale" />
      <span className="sheet-tag__ticks">0 · 50 · 100 · 200 M</span>
    </div>
  );
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const STATUS_TEXT: Record<LiveCall['callStatus'], string> = {
  idle: 'starting',
  ringing: 'ringing',
  'in-progress': 'in progress',
  completed: 'completed',
  'no-answer': 'no answer',
};

export function LiveCallBanner({ live, elapsedS }: { live: LiveCall; elapsedS: number }) {
  return (
    <div className="live-banner" role="status">
      <i className={cx(live.phase === 'running' && 'is-pulsing')} />
      <div>
        <strong>
          LIVE · Calling DEMO_PHONE · {STATUS_TEXT[live.callStatus]} {fmt(elapsedS)}
        </strong>
        <span>{live.source === 'fallback' ? 'Fallback · live_fallback.json' : 'call_status from /api/live · fallback ready'}</span>
      </div>
    </div>
  );
}

export function ResultsCard({ r, onClose }: { r: Results; onClose: () => void }) {
  const pct = (v: number) => `${Math.round(v)}%`;
  return (
    <section className="results" aria-label="Demo results">
      <div className="row-between">
        <div>
          <h2>Demo results</h2>
          <span className="results__sub">Harvey replay · {r.n_households} households · results.json</span>
        </div>
        <button type="button" className="btn btn--ghost btn--small" onClick={onClose}>
          Close
        </button>
      </div>
      <span className="eyebrow eyebrow--tight">At-risk households reached before water arrives</span>
      <div className="results__bar">
        <div className="row-between results__bar-head">
          <span>Baseline (sirens + manual calls)</span>
          <strong>{pct(r.baseline_pct)}</strong>
        </div>
        <div className="track">
          <i style={{ width: pct(r.baseline_pct), background: 'var(--text-dim)' }} />
        </div>
      </div>
      <div className="results__bar">
        <div className="row-between results__bar-head">
          <span>Swift</span>
          <strong className="is-accent">{pct(r.swift_pct)}</strong>
        </div>
        <div className="track">
          <i style={{ width: pct(r.swift_pct), background: 'var(--accent)' }} />
        </div>
      </div>
      <div className="mc">
        <div className="row-between">
          <span>{r.mc.n.toLocaleString()}-night Monte Carlo (Swift)</span>
          <span className="mono-strong">
            p10 {pct(r.mc.p10)} – p90 {pct(r.mc.p90)}
          </span>
        </div>
        <div className="mc__range">
          <i className="mc__axis" />
          <i className="mc__band" style={{ left: pct(r.mc.p10), width: `${r.mc.p90 - r.mc.p10}%` }} />
          <i className="mc__tick mc__tick--swift" style={{ left: pct(r.mc.median_swift) }} />
          <i className="mc__tick mc__tick--base" style={{ left: pct(r.mc.median_baseline) }} />
        </div>
        <div className="row-between mc__labels">
          <span>0%</span>
          <span>baseline {pct(r.mc.median_baseline)}</span>
          <span>median {pct(r.mc.median_swift)}</span>
          <span>100%</span>
        </div>
      </div>
      <div className="results__tiles">
        <div className="tile">
          <span>Extraction accuracy</span>
          <strong>{r.record_accuracy.toFixed(2)}</strong>
          <small>≥ 0.85 target</small>
        </div>
        <div className={cx('tile', r.promise_violations === 0 && 'tile--good')}>
          <span>Promise violations</span>
          <strong>{r.promise_violations}</strong>
          <small>guard blocked {r.promises_blocked} before speaking</small>
        </div>
        <div className="tile">
          <span>Peak parallel calls</span>
          <strong>{r.parallel_calls}</strong>
          <small>on the GB10</small>
        </div>
      </div>
    </section>
  );
}
