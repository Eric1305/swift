import type { Briefing, DisplayStatus, QueueSnapshot } from '../data/types';
import type { LiveRow } from '../demo/liveQueue';
import type { Counts } from '../demo/timeline';
import { formatT } from '../demo/timeline';
import { statusVar } from '../map/colors';
import { Dot, Eyebrow } from './ui';
import cx from './cx';
import swiftLogo from '../assets/swift-logo.png';

interface Props {
  counts: Counts;
  queue: QueueSnapshot['ranked'];
  addresses: Map<string, string>;
  statuses: Map<string, DisplayStatus>;
  briefing: Briefing | null;
  selectedId: string | null;
  onPick: (id: string) => void;
  /** ?layout=lean: compact counters, live soonest-water queue, briefing lives in the model card. */
  lean?: LiveRow[] | null;
}

const COUNTERS: { key: keyof Counts; label: string; dot: DisplayStatus | 'called' }[] = [
  { key: 'called', label: 'Called', dot: 'called' },
  { key: 'needs_help', label: 'Needs help', dot: 'needs_help' },
  { key: 'can_help', label: 'Can help', dot: 'can_help' },
  { key: 'safe', label: 'Safe', dot: 'safe' },
  { key: 'no_answer', label: 'No answer', dot: 'no_answer' },
  { key: 'not_called', label: 'Not called', dot: 'not_called' },
];

const BAR: DisplayStatus[] = ['needs_help', 'can_help', 'safe', 'unconfirmed', 'no_answer', 'calling'];

const LEAN_COUNTERS: { key: keyof Counts; label: string; dot: DisplayStatus | 'called' }[] = [
  { key: 'called', label: 'Called', dot: 'called' },
  { key: 'needs_help', label: 'Need help', dot: 'needs_help' },
  { key: 'can_help', label: 'Can help', dot: 'can_help' },
  { key: 'safe', label: 'Safe', dot: 'safe' },
  { key: 'no_answer', label: 'No answer', dot: 'no_answer' },
];

function LeanPanel({ counts, rows, selectedId, onPick }: { counts: Counts; rows: LiveRow[]; selectedId: string | null; onPick: (id: string) => void }) {
  const open = rows.filter((r) => r.state !== 'picked');
  const picked = rows.length - open.length;
  return (
    <aside className="panel left-panel left-panel--lean" aria-label="Call progress">
      <div className="row-between">
        <h2 className="panel-title">Call progress</h2>
        <span className="mono-meta">{counts.called} / {counts.total} called</span>
      </div>
      <div className="lean-counters">
        {LEAN_COUNTERS.map((c) => (
          <div key={c.key} className="lean-counter">
            <strong>{counts[c.key]}</strong>
            <span><Dot status={c.dot} size={6} />{c.label}</span>
          </div>
        ))}
      </div>
      <div className="status-bar" role="img" aria-label="Status mix">
        {BAR.map((s) =>
          counts[s] ? <i key={s} className={`status-bar__seg status-bar__seg--${s}`} style={{ width: `${(counts[s] / counts.total) * 100}%`, background: statusVar(s) }} /> : null,
        )}
      </div>
      <section className="queue">
        <div className="row-between">
          <Eyebrow>Rescue queue</Eyebrow>
          <span className="hint">{picked ? `${picked} picked up · ` : ''}soonest water first</span>
        </div>
        {open.length === 0 ? (
          <div className="queue__empty">
            <img src={swiftLogo} width={64} height={64} alt="" />
            <strong>{picked ? 'Everyone in the queue is picked up' : 'No one in the queue yet'}</strong>
            <span>{picked ? 'Door-knock homes appear here as their water approaches.' : 'Households that need help appear here as calls complete.'}</span>
          </div>
        ) : (
          <ol className="queue__list">
            {open.map((r) => (
              <li key={r.id}>
                <button type="button" className={cx('lean-row', `lean-row--${r.state}`, selectedId === r.id && 'is-selected')} onClick={() => onPick(r.id)}>
                  <span className="lean-row__top">
                    <strong>{r.address}</strong>
                    <span className="lean-row__eta">{r.label}</span>
                  </span>
                  <span className="lean-row__need">{r.need}</span>
                  {r.crew && <span className="lean-row__crew">{r.crew}</span>}
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>
    </aside>
  );
}

export default function LeftPanel({ counts, queue, addresses, statuses, briefing, selectedId, onPick, lean }: Props) {
  if (lean) return <LeanPanel counts={counts} rows={lean} selectedId={selectedId} onPick={onPick} />;
  return (
    <aside className="panel left-panel" aria-label="Call progress">
      <div className="row-between">
        <h2 className="panel-title">Call progress</h2>
        <span className="mono-meta">
          {counts.called} / {counts.total} called
        </span>
      </div>

      <div className="counters">
        {COUNTERS.map((c) => (
          <div key={c.key} className="counter">
            <span className="counter__label">
              <Dot status={c.dot} size={7} />
              {c.label}
            </span>
            <strong className="counter__value">{counts[c.key]}</strong>
          </div>
        ))}
      </div>

      <div className="status-bar" role="img" aria-label="Status mix">
        {BAR.map((s) =>
          counts[s] ? <i key={s} className={`status-bar__seg status-bar__seg--${s}`} style={{ width: `${(counts[s] / counts.total) * 100}%`, background: statusVar(s) }} /> : null,
        )}
      </div>

      <section className="queue">
        <div className="row-between">
          <Eyebrow>Rescue queue</Eyebrow>
          <span className="hint">ranked by risk · click to fly</span>
        </div>
        {queue.length === 0 ? (
          <div className="queue__empty">
            <img src={swiftLogo} width={64} height={64} alt="" />
            <strong>No one in the queue yet</strong>
            <span>Households that need help are ranked here as calls complete.</span>
          </div>
        ) : (
          <ol className="queue__list">
            {queue.map((q, k) => {
              const st = statuses.get(q.household_id) ?? 'needs_help';
              return (
                <li key={q.household_id}>
                  <button
                    type="button"
                    className={cx('queue-row', selectedId === q.household_id && 'is-selected')}
                    onClick={() => onPick(q.household_id)}
                    style={{ ['--sev' as string]: statusVar(st === 'calling' ? 'needs_help' : st) }}
                  >
                    <span className="queue-row__rank">{k + 1}</span>
                    <span className="queue-row__body">
                      <strong>{addresses.get(q.household_id) ?? q.household_id}</strong>
                      <span>{q.reasons.join(' · ')}</span>
                    </span>
                    <span className="queue-row__score">{Math.round(q.score)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section className="briefing">
        <div className="row-between">
          <Eyebrow className="eyebrow--tight">Commander briefing{briefing ? ` · ${formatT(briefing.t_min)}` : ''}</Eyebrow>
          <span className="tag-accent">Qwen · GB10</span>
        </div>
        <p className={cx(!briefing && 'is-empty')}>{briefing ? briefing.text : 'No briefing yet. The first commander briefing appears once calls start.'}</p>
      </section>
    </aside>
  );
}
