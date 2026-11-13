import { useEffect, useRef } from 'react';
import type { CallStatus, DisplayStatus, HouseholdProps, HouseholdRecord, TranscriptLine } from '../data/types';
import { formatT } from '../demo/timeline';
import { Button, Eyebrow, StatusChip } from './ui';
import cx from './cx';
import closeIcon from '../assets/icons/close.svg';
import swiftLogo from '../assets/swift-logo.png';

const LANG: Record<string, string> = { en: 'English', es: 'Spanish', vi: 'Vietnamese', zh: 'Chinese' };

export interface LiveInfo {
  callStatus: CallStatus;
  source: 'api' | 'fallback';
  elapsedS: number;
}

interface Props {
  household: HouseholdProps;
  status: DisplayStatus;
  record: HouseholdRecord | null;
  transcript: TranscriptLine[];
  rank: number | null;
  live: LiveInfo | null;
  onClose: () => void;
  onFly: () => void;
}

const fmtElapsed = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

function fields(r: HouseholdRecord | null, live: boolean): [string, string, boolean][] {
  const pending = (v: string | null) => (v === null ? [live ? 'listening…' : '—', true] as const : [v, false] as const);
  const people = r?.people ?? null;
  const cant = r?.cant_leave_alone?.length ? r.cant_leave_alone.map((c) => `${c.who} — ${c.need}`).join('; ') : r && !(live && r.water_inside === null) ? 'No one' : null;
  const water = r?.water_inside == null ? null : r.water_inside ? 'Yes' : 'No';
  const help = r ? [r.can_help.truck && 'truck', r.can_help.boat && 'boat', r.can_help.seats > 0 && `${r.can_help.seats} seats`].filter(Boolean).join(', ') || '—' : null;
  const rows: [string, string | null][] = [
    ['People', people === null ? null : String(people)],
    ['Can’t leave alone', cant],
    ['Water inside', water],
    ['Can help', help],
    ['Language', r ? LANG[r.language] ?? r.language : null],
    ['Attempts', r ? `${r.attempts}${r.status === 'no_answer' ? ' (no answer)' : ' (answered)'}` : null],
  ];
  return rows.map(([k, v]) => {
    const [text, isPending] = pending(v);
    return [k, text, isPending];
  });
}

const STEPS: { key: CallStatus; label: string }[] = [
  { key: 'ringing', label: 'Ringing' },
  { key: 'in-progress', label: 'In progress' },
  { key: 'completed', label: 'Completed' },
];

export default function HouseholdDrawer({ household, status, record, transcript, rank, live, onClose, onFly }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' });
  }, [transcript.length]);

  const stepIndex = live ? STEPS.findIndex((s) => s.key === live.callStatus) : -1;
  const card = record?.house_card ?? null;

  return (
    <aside className="drawer" aria-label={`Household ${household.address}`}>
      <div className="row-between">
        <div className="drawer__status">
          <span className={cx('drawer__mascot', status === 'needs_help' && 'drawer__mascot--urgent')} aria-hidden="true">
            <img src={swiftLogo} width={52} height={52} alt="" />
            {status === 'needs_help' && <span className="drawer__mascot-alert">!</span>}
          </span>
          <StatusChip status={status} />
        </div>
        <span className="drawer__meta">
          {live ? 'Live call' : rank ? `#${rank} in queue` : household.id}
          <button type="button" className="drawer__close" aria-label="Close" onClick={onClose}>
            <img src={closeIcon} width={14} height={14} alt="" />
          </button>
        </span>
      </div>

      <div className="drawer__title">
        <h2>{household.address}</h2>
        <p>
          {live
            ? 'Calling the presenter’s phone · every reply decided by Qwen on the GB10; Retell handles voice only'
            : household.water_arrival_min == null
              ? `${household.id} · no flooding predicted at this home`
              : `${household.id} · predicted water arrival ${formatT(household.water_arrival_min)} · peak depth ${household.depth_ft_peak.toFixed(1)} ft`}
        </p>
      </div>

      {live && (
        <div className="call-steps" aria-label="Call status">
          {STEPS.map((s, k) => {
            const state = live.callStatus === 'no-answer' && k === 2 ? 'failed' : k < stepIndex || live.callStatus === 'completed' ? 'done' : k === stepIndex ? 'active' : 'todo';
            return (
              <span key={s.key} className="call-steps__item">
                {k > 0 && <i className="call-steps__line" />}
                <span className={cx('call-step', `call-step--${state}`)}>
                  <i />
                  {k === 2 && live.callStatus === 'no-answer' ? 'No answer' : s.label}
                  {state === 'active' && k === 1 ? ` · ${fmtElapsed(live.elapsedS)}` : ''}
                </span>
              </span>
            );
          })}
        </div>
      )}

      <dl className="record">
        {fields(record, !!live && live.callStatus !== 'completed').map(([k, v, pending]) => (
          <div key={k} className="record__row">
            <dt>{k}</dt>
            <dd className={cx(pending && 'is-pending')}>{v}</dd>
          </div>
        ))}
      </dl>

      <section className={cx('house-card', card ? 'house-card--filled' : 'house-card--empty')} style={{ ['--card' as string]: card ? 'var(--status-needs-help)' : 'var(--border)' }}>
        <div className="row-between">
          <Eyebrow>Responder house card</Eyebrow>
          <span className="mono-dim">≤40 words · Qwen</span>
        </div>
        <p>{card ?? (live ? 'Written when the call ends.' : 'No house card for this household.')}</p>
      </section>

      <section className="transcript">
        <div className="row-between">
          <Eyebrow>Transcript</Eyebrow>
          <span className="hint">{live ? `${live.source === 'fallback' ? 'fallback' : 'streaming'} · /api/live every 2 s` : `${transcript.length} turns`}</span>
        </div>
        <div className="transcript__list" ref={scroller}>
          {transcript.length === 0 && <p className="hint">{live ? 'Waiting for the resident to pick up…' : 'No transcript (no answer).'}</p>}
          {transcript.map((line, k) => (
            <div key={k} className={cx('bubble', `bubble--${line.who}`)}>
              <span>{line.who === 'agent' ? 'Swift agent' : 'Resident'}</span>
              <p>{line.text}</p>
            </div>
          ))}
          {live && live.callStatus !== 'completed' && live.callStatus !== 'no-answer' && (
            <div className="bubble bubble--resident bubble--typing" aria-label="Listening">
              <i />
              <i />
              <i />
            </div>
          )}
        </div>
      </section>

      <footer className="drawer__footer">
        <p className="mono-meta">
          {live
            ? live.source === 'fallback'
              ? 'API unavailable · playing live_fallback.json'
              : 'If /api/live fails or 90 s pass → play live_fallback.json'
            : record
              ? `${record.attempts} attempt${record.attempts === 1 ? '' : 's'} · status ${record.status}`
              : 'No record yet'}
        </p>
        <div className="drawer__actions">
          <Button onClick={onFly}>Fly to house</Button>
          <Button variant="ghost" disabled={!card} onClick={() => card && navigator.clipboard?.writeText(card)}>
            Copy house card
          </Button>
        </div>
      </footer>
    </aside>
  );
}
