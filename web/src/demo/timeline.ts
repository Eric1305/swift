import type { Briefing, DisplayStatus, QueueSnapshot, TimelineEvent } from '../data/types';

/** Folds timeline events up to minute `t` into a status per household. */
export function statusAt(timeline: TimelineEvent[], t: number): Map<string, DisplayStatus> {
  const out = new Map<string, DisplayStatus>();
  for (const e of timeline) {
    if (e.t_min > t) break;
    switch (e.event) {
      case 'call_start':
      case 'retry':
        out.set(e.household_id, 'calling');
        break;
      case 'no_answer':
        out.set(e.household_id, 'no_answer');
        break;
      case 'complete':
        out.set(e.household_id, e.status ?? 'unconfirmed');
        break;
    }
  }
  return out;
}

export interface Counts {
  called: number;
  needs_help: number;
  can_help: number;
  safe: number;
  unconfirmed: number;
  no_answer: number;
  calling: number;
  not_called: number;
  total: number;
}

export function countStatuses(ids: string[], statuses: Map<string, DisplayStatus>): Counts {
  const c: Counts = { called: 0, needs_help: 0, can_help: 0, safe: 0, unconfirmed: 0, no_answer: 0, calling: 0, not_called: 0, total: ids.length };
  for (const id of ids) {
    const s = statuses.get(id) ?? 'not_called';
    c[s] += 1;
    if (s !== 'not_called') c.called += 1;
  }
  return c;
}

/** Latest entry with t_min ≤ t (input sorted by t_min). */
export function latestAt<T extends { t_min: number }>(items: T[], t: number): T | null {
  let found: T | null = null;
  for (const it of items) {
    if (it.t_min > t) break;
    found = it;
  }
  return found;
}

export const queueAt = (q: QueueSnapshot[], t: number) => latestAt(q, t)?.ranked ?? [];
export const briefingAt = (b: Briefing[], t: number) => latestAt(b, t);

const pad = (n: number) => String(Math.floor(n)).padStart(2, '0');

/** Minutes since start → "T+hh:mm". */
export function formatT(min: number): string {
  const m = Math.max(0, Math.floor(min));
  return `T+${pad(m / 60)}:${pad(m % 60)}`;
}

/** Wall-clock label for minute `min` of the replay, in the replay's own offset; `scale` real minutes per replay minute. */
export function formatClock(startIso: string, min: number, scale = 1): string {
  const start = new Date(startIso);
  const offsetMatch = /([+-])(\d\d):?(\d\d)$/.exec(startIso);
  const offsetMin = offsetMatch ? (offsetMatch[1] === '-' ? -1 : 1) * (Number(offsetMatch[2]) * 60 + Number(offsetMatch[3])) : 0;
  const local = new Date(start.getTime() + (min * scale + offsetMin) * 60_000);
  const day = local.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).replace(/,/g, '');
  const zone = offsetMin === -300 ? 'CDT' : offsetMin === -360 ? 'CST' : `UTC${offsetMatch?.[0] ?? ''}`;
  return `${day} · ${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())} ${zone}`;
}
