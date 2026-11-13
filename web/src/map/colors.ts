import type { DisplayStatus, ImageryItem, Vehicle } from '../data/types';

export type RGBA = [number, number, number, number];

const hex = (h: string, a = 255): RGBA => {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, a];
};

/**
 * Soft household status colors on the map, with muted edges to keep pale roofs distinct
 * from the surrounding context buildings.
 */
export const ROOF: Record<DisplayStatus, RGBA> = {
  needs_help: hex('#F5B8BE'),
  can_help: hex('#F6D5AA'),
  safe: hex('#B6E4CA'),
  unconfirmed: hex('#F1E2AC'),
  no_answer: hex('#CBD7E6'),
  not_called: hex('#D8DCE2'),
  calling: hex('#38BDF8'),
};

/** Muted edge of each status: roof wireframe, ground-disc ring. */
export const EDGE: Record<DisplayStatus, RGBA> = {
  needs_help: hex('#C47C86'),
  can_help: hex('#BE9869'),
  safe: hex('#79AB90'),
  unconfirmed: hex('#B3A06A'),
  no_answer: hex('#899BB2'),
  not_called: hex('#9CA6B3'),
  calling: hex('#0369A1'),
};

/** Statuses an operator has to act on: get a larger pin and an address label. */
export const ACTIONABLE = new Set<DisplayStatus>(['needs_help', 'no_answer', 'calling']);

export const VEHICLE: Record<Vehicle, RGBA> = {
  hwv: hex('#F97316'),
  boat: hex('#22D3EE'),
  neighbor_truck: hex('#F6D5AA'),
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
