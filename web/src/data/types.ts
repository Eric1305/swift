// Shapes from CONTRACT.md. The frontend reads only these.

export type LonLat = [number, number];

export type Status = 'needs_help' | 'can_help' | 'safe' | 'unconfirmed' | 'no_answer' | 'not_called';
/** `calling` is derived by the frontend while a call rings or is in progress. */
export type DisplayStatus = Status | 'calling';

export interface DepthStage {
  t_min: number;
  png: string;
  bounds: [LonLat, LonLat];
}

export interface Meta {
  demo_household_id: string;
  center: LonLat;
  zoom: number;
  pitch: number;
  bearing: number;
  /** time_scale: real minutes per replay minute (the replay compresses Harvey's pool rise). */
  timeline: { start_iso: string; end_min: number; step_min: number; time_scale?: number };
  staging: LonLat;
  hub: LonLat;
  depth_stages: DepthStage[];
}

export interface HouseholdProps {
  id: string;
  address: string;
  /** null = the recorded Harvey pool never reached this home. */
  water_arrival_min: number | null;
  depth_ft_peak: number;
  height_m: number;
}

export interface HouseholdFeature {
  type: 'Feature';
  geometry: { type: 'Polygon'; coordinates: LonLat[][] };
  properties: HouseholdProps;
}

export interface TimelineEvent {
  t_min: number;
  household_id: string;
  event: 'call_start' | 'retry' | 'no_answer' | 'complete';
  status?: Status;
}

export interface TranscriptLine {
  who: 'agent' | 'resident';
  text: string;
}

export interface HouseholdRecord {
  id: string;
  status: Status;
  people: number | null;
  cant_leave_alone: { who: string; need: string }[];
  water_inside: boolean | null;
  can_help: { truck: boolean; boat: boolean; seats: number };
  language: string;
  transcript: TranscriptLine[];
  house_card: string | null;
  attempts: number;
}

export interface QueueSnapshot {
  t_min: number;
  ranked: { household_id: string; score: number; reasons: string[] }[];
}

export type Vehicle = 'hwv' | 'boat' | 'neighbor_truck' | 'neighbor_boat';

export interface Route {
  vehicle_id: string;
  vehicle: Vehicle;
  to_household_id: string;
  path: LonLat[];
  timestamps: number[];
}

export interface DoorknockFeature {
  type: 'Feature';
  geometry: { type: 'Polygon'; coordinates: LonLat[][] };
  properties: { t_min: number; household_ids: string[] };
}

export interface Briefing {
  t_min: number;
  text: string;
}

export interface ImageryItem {
  image_id: string;
  lon: number;
  lat: number;
  /** Georeferenced footprint of the aerial: [[w,s],[e,n]]. */
  bounds: [LonLat, LonLat];
  /** Post-Harvey aerial (2017). */
  thumb: string;
  /** Pre-storm aerial of the same tile, when available. */
  before_thumb: string | null;
  date: string;
  rain_3d_mm: number;
  verdict: 'flooded' | 'not_flooded' | 'uncertain';
  explanation: string;
}

export interface Results {
  baseline_pct: number;
  swift_pct: number;
  record_accuracy: number;
  /** Promises actually spoken to residents (should be 0). */
  promise_violations: number;
  /** Model lines the honesty guard caught before they were spoken. */
  promises_blocked: number;
  parallel_calls: number;
  n_households: number;
  mc: { median_baseline: number; median_swift: number; p10: number; p90: number; n: number; seconds: number };
}

export interface LiveFallback {
  record: HouseholdRecord;
  steps: { delay_ms: number; who: TranscriptLine['who']; text: string }[];
}

export interface GpuStats {
  gpu_util: number;
  mem_used_gb: number;
  mem_total_gb: number;
  temp_c: number;
  /** LLM requests in flight on the hosted GB10 model. */
  llm_running: number;
  /** Total LLM calls served. */
  llm_calls: number;
  latency_ms: number;
}

export type CallStatus = 'idle' | 'ringing' | 'in-progress' | 'completed' | 'no-answer';

export interface LiveResponse {
  record: HouseholdRecord | null;
  call_status: CallStatus;
}

export interface Fixtures {
  meta: Meta;
  households: HouseholdFeature[];
  timeline: TimelineEvent[];
  queue: QueueSnapshot[];
  routes: Route[];
  doorknock: DoorknockFeature[];
  briefings: Briefing[];
  imagery: ImageryItem[];
  results: Results;
  liveFallback: LiveFallback;
  gpuSample: GpuStats;
}
