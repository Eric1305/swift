import type { DisplayStatus, ImageryItem, Vehicle } from '../data/types';

export type RGBA = [number, number, number, number];

const hex = (h: string, a = 255): RGBA => {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, a];
};

/** Roof colors on the site-plan map. Unreached homes stay white like context buildings. */
export const ROOF: Record<DisplayStatus, RGBA> = {
  needs_help: hex('#EF4444'),
  can_help: hex('#F59E0B'),
  safe: hex('#22C55E'),
  unconfirmed: hex('#EAB308'),
  no_answer: hex('#111827'),
  not_called: hex('#FCFBF8'),
  calling: hex('#38BDF8'),
};

export const VEHICLE: Record<Vehicle, RGBA> = {
  hwv: hex('#F97316'),
  boat: hex('#22D3EE'),
  neighbor_truck: hex('#F59E0B'),
  neighbor_boat: hex('#FCD34D'),
};

export const INK = hex('#1E2433');
export const NAVY = hex('#2B3354');

/** CSS var name for a status (used by chips, counters, bars). */
export const statusVar = (s: DisplayStatus) => `var(--status-${s.replace('_', '-')})`;

export const VERDICT: Record<ImageryItem['verdict'], { label: string; color: string }> = {
  flooded: { label: 'Flooded', color: 'var(--status-needs-help)' },
  uncertain: { label: 'Uncertain', color: 'var(--status-unconfirmed)' },
  not_flooded: { label: 'Not flooded', color: 'var(--status-safe)' },
};
