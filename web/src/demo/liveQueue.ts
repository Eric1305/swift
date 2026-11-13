import type { DisplayStatus, HouseholdProps, QueueSnapshot, Route, Vehicle } from '../data/types';

/** Lean-layout rescue queue: soonest water first, with crew status from the real routes. */
export type RowState = 'picked' | 'under' | 'soon' | 'later' | 'knock';

export interface LiveRow {
  id: string;
  address: string;
  need: string;
  state: RowState;
  label: string;
  crew: string | null;
}

const VEHICLE: Record<Vehicle, string> = {
  hwv: 'High-water truck',
  boat: 'Rescue boat',
  neighbor_truck: "Neighbor's truck",
  neighbor_boat: "Neighbor's boat",
};

const isDetail = (r: string) => /ft peak|water in ~|^water inside$/.test(r);

function untilText(min: number): string {
  if (min < 60) return `water in ${Math.max(1, Math.round(min))} min`;
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return `water in ${h}h ${m.toString().padStart(2, '0')}m`;
}

export function liveQueue(
  t: number,
  statuses: Map<string, DisplayStatus>,
  households: Map<string, HouseholdProps>,
  finalQueue: QueueSnapshot | undefined,
  routes: Route[],
): LiveRow[] {
  const reasons = new Map((finalQueue?.ranked ?? []).map((r) => [r.household_id, r.reasons]));
  const routeTo = new Map(routes.map((r) => [r.to_household_id, r]));
  const rows: (LiveRow & { order: number })[] = [];
  for (const [id, status] of statuses) {
    const home = households.get(id);
    if (!home) continue;
    const arrival = home.water_arrival_min;
    const knock = status === 'no_answer';
    if (!(status === 'needs_help' || (knock && arrival != null))) continue;

    const why = reasons.get(id) ?? [];
    const need = knock
      ? 'No answer after 3 tries · door knock'
      : [...why.filter((r) => !isDetail(r)), ...(why.includes('water inside') ? ['water inside'] : [])].join(' · ') || 'needs help leaving';

    const route = knock ? undefined : routeTo.get(id);
    const depart = route?.timestamps[0];
    const pickup = route?.timestamps[route.timestamps.length - 1];
    let state: RowState;
    let label: string;
    if (pickup != null && pickup <= t) {
      state = 'picked';
      label = '✓ picked up';
    } else if (arrival != null && t >= arrival) {
      state = 'under';
      label = 'under water';
    } else if (arrival == null) {
      state = 'later';
      label = 'help requested';
    } else {
      state = knock ? 'knock' : arrival - t <= 30 ? 'soon' : 'later';
      label = untilText(arrival - t);
    }
    let crew: string | null = null;
    if (route && pickup != null && pickup > t && depart != null) {
      crew = t >= depart ? `${VEHICLE[route.vehicle]} en route · ${Math.max(1, Math.ceil(pickup - t))} min` : `${VEHICLE[route.vehicle]} assigned`;
    }
    const order = state === 'picked' ? 1e7 + (pickup ?? 0) : arrival ?? 1e6;
    rows.push({ id, address: home.address, need, state, label, crew, order });
  }
  return rows.sort((a, b) => a.order - b.order).map(({ order: _order, ...row }) => row);
}
