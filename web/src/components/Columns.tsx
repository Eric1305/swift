import { useState, type CSSProperties, type ReactNode } from 'react';
import type { DisplayStatus, HouseholdProps, Route, Vehicle } from '../data/types';
import type { Counts } from '../demo/timeline';
import type { LiveRow } from '../demo/liveQueue';
import { SPEEDS, type Clock } from '../demo/useClock';
import { formatT } from '../demo/timeline';
import { IconButton } from './ui';
import cx from './cx';
import playIcon from '../assets/icons/play.svg';
import pauseIcon from '../assets/icons/pause.svg';

/** Collapsible card: title, count on the right, chevron. */
export function Card({ title, count, children, defaultOpen = true, className }: { title: string; count?: ReactNode; children: ReactNode; defaultOpen?: boolean; className?: string }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={cx('card', !open && 'is-collapsed', className)}>
      <button type="button" className="card__head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <strong>{title}</strong>
        <span className="card__count">{count}</span>
        <i className="card__chevron" aria-hidden />
      </button>
      {open && <div className="card__body">{children}</div>}
    </section>
  );
}

const VEHICLE_NAME: Record<Vehicle, string> = { hwv: 'High-water truck', boat: 'Rescue boat', neighbor_truck: "Neighbor's truck", neighbor_boat: "Neighbor's boat" };

export function LeftColumn({ counts, pickedUp, rows, selectedId, onPick }: { counts: Counts; pickedUp: number; rows: LiveRow[]; selectedId: string | null; onPick: (id: string) => void }) {
  // Door-knock homes have their own card on the right; this queue is people who asked for help.
  const open = rows.filter((r) => r.state !== 'picked' && r.state !== 'knock' && !r.need.startsWith('No answer'));
  return (
    <div className="column column--left">
      <Card title="Homes in the zone" count={counts.total}>
        <div className="zone-bar"><i style={{ width: `${(counts.called / counts.total) * 100}%` }} /></div>
        <div className="zone-stats">
          <div><strong className="is-red">{counts.needs_help}</strong><span><i className="sw sw--red" />Need help</span></div>
          <div><strong>{counts.no_answer}</strong><span><i className="sw sw--ink" />No answer</span></div>
          <div><strong>{pickedUp}</strong><span><i className="sw sw--ring" />Picked up</span></div>
        </div>
        <p className="zone-note">{counts.called} of {counts.total} called · {counts.can_help} can help · {counts.safe} safe</p>
      </Card>
      <Card title="Rescue queue" count={open.length || ''} className={open.length ? 'card--grow' : undefined}>
        {open.length === 0 ? (
          <p className="card__empty">{rows.length ? 'Everyone who asked for help is picked up.' : 'Nobody has asked for help yet.'}</p>
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
      </Card>
    </div>
  );
}

interface CrewLine { id: string; name: string; doing: string; done: number; active: boolean }

function crews(routes: Route[], t: number, addresses: Map<string, string>): CrewLine[] {
  const byVehicle = new Map<string, Route[]>();
  for (const r of routes) byVehicle.set(r.vehicle_id, [...(byVehicle.get(r.vehicle_id) ?? []), r]);
  const lines: CrewLine[] = [];
  for (const [id, trips] of byVehicle) {
    trips.sort((a, b) => a.timestamps[0] - b.timestamps[0]);
    const kind = trips[0].vehicle;
    const done = trips.filter((r) => r.timestamps[r.timestamps.length - 1] <= t).length;
    const now = trips.find((r) => r.timestamps[0] <= t && t < r.timestamps[r.timestamps.length - 1]);
    const next = trips.find((r) => r.timestamps[0] > t);
    const home = kind.startsWith('neighbor') ? 'At home' : 'At staging';
    const doing = now
      ? `Driving to ${addresses.get(now.to_household_id) ?? now.to_household_id}`
      : next
        ? `${home} · next: ${addresses.get(next.to_household_id) ?? next.to_household_id}`
        : done
          ? `${home} · done`
          : home;
    const num = id.match(/\d+$/)?.[0];
    const name = kind.startsWith('neighbor') ? `${VEHICLE_NAME[kind]} · ${addresses.get(id.replace('nbr-', '')) ?? ''}` : `${VEHICLE_NAME[kind]}${num ? ` ${num}` : ''}`;
    lines.push({ id, name, doing, done, active: Boolean(now) });
  }
  const neighbor = (l: CrewLine) => (l.id.startsWith('nbr') ? 1 : 0);
  return lines.sort((a, b) => Number(b.active) - Number(a.active) || neighbor(a) - neighbor(b) || a.id.localeCompare(b.id));
}

export function RightColumn({ routes, t, addresses, statuses, households, onPick, children }: {
  routes: Route[]; t: number; addresses: Map<string, string>; statuses: Map<string, DisplayStatus>;
  households: Map<string, HouseholdProps>; onPick: (id: string) => void; children: ReactNode;
}) {
  const started = routes.filter((r) => r.timestamps[0] <= t);
  const lines = crews(started.length ? routes : [], t, addresses);
  const onRoad = lines.filter((l) => l.active).length;
  const doors = [...statuses].filter(([, s]) => s === 'no_answer').map(([id]) => id)
    .sort((a, b) => (households.get(a)?.water_arrival_min ?? 1e6) - (households.get(b)?.water_arrival_min ?? 1e6));
  return (
    <div className="column column--right">
      <Card title="Rescue crews" count={lines.length ? `${onRoad} on the road` : ''}>
        {lines.length === 0 ? <p className="card__empty">No crews dispatched yet.</p> : (
          <ul className="crew-list">
            {lines.slice(0, 6).map((l) => (
              <li key={l.id} className={cx(l.active && 'is-active')}>
                <i className={cx('crew-dot', l.active && 'is-active')} />
                <span><strong>{l.name}</strong><em>{l.doing}</em></span>
                <span className="crew-done">{l.done}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Doors to knock" count={doors.length || ''}>
        {doors.length === 0 ? <p className="card__empty">No unanswered homes yet.</p> : (
          <>
            <p className="card__note">Homes that never picked up, in the order their water arrives.</p>
            <ol className="door-list">
              {doors.slice(0, 5).map((id, k) => {
                const arrival = households.get(id)?.water_arrival_min;
                return (
                  <li key={id}>
                    <button type="button" onClick={() => onPick(id)}>
                      <span className="door-n">{k + 1}</span>
                      <span className="door-addr">{addresses.get(id)}</span>
                      <span className="door-eta">{arrival == null ? 'dry' : arrival <= t ? 'under water' : `T${formatT(arrival).slice(1)}`}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </Card>
      {children}
    </div>
  );
}

export function PlaybackBar({ clock }: { clock: Clock }) {
  const progress = clock.endMin ? clock.t / clock.endMin : 0;
  return (
    <div className="playback">
      <div className="playback__row">
        <IconButton icon={clock.playing ? pauseIcon : playIcon} label={clock.playing ? 'Pause' : 'Play'} onClick={clock.toggle} />
        <div className="speed" role="radiogroup" aria-label="Playback speed">
          {SPEEDS.map((s) => (
            <button key={s} type="button" role="radio" aria-checked={clock.speed === s} className={cx('speed__opt', clock.speed === s && 'is-active')} onClick={() => clock.setSpeed(s)}>
              {s}×
            </button>
          ))}
        </div>
        <input className="scrubber" type="range" min={0} max={clock.endMin} step={0.5} value={clock.t}
          onChange={(e) => clock.seek(Number(e.target.value))} aria-label="Replay time" style={{ '--progress': `${progress * 100}%` } as CSSProperties} />
        <span className="playback__t">{formatT(clock.t)}</span>
      </div>
      <div className="playback__legend">
        <span className="playback__swatch" />
        <span>Water depth: Addicks Reservoir level recorded by USGS in Harvey</span>
        <span className="playback__scale">shallow → 6+ ft</span>
      </div>
    </div>
  );
}
