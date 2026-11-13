# Swift data contract

The frontend reads **only** these files from `web/public/data/` plus the live endpoints below.
The backend pipeline overwrites the sample files with real ones; shapes never change.
All times are **minutes since the start of the replay** (`t_min`). Coordinates are `[lon, lat]`.

## Status values
| status | color | meaning |
|---|---|---|
| `needs_help` | `#ef4444` | someone can't leave alone, or water is inside |
| `can_help` | `#f59e0b` | has a truck, boat or free seats |
| `safe` | `#22c55e` | can get out on their own |
| `unconfirmed` | `#eab308` | answered but details couldn't be confirmed |
| `no_answer` | `#111827` + white outline | no pickup after 2 retries → door-knock list |
| `not_called` | `#6b7280` | not called yet |

While a call is ringing or in progress the frontend shows the derived state `calling` (pulse).

## Files
| File | Shape |
|---|---|
| `meta.json` | `{demo_household_id, center:[lon,lat], zoom, pitch, bearing, timeline:{start_iso, end_min, step_min}, staging:[lon,lat], hub:[lon,lat], depth_stages:[{t_min, png, bounds:[[w,s],[e,n]]}]}` |
| `households.geojson` | FeatureCollection of Polygon footprints, `properties:{id, address, water_arrival_min, depth_ft_peak, height_m}` |
| `timeline.json` | `[{t_min, household_id, event:"call_start"\|"retry"\|"no_answer"\|"complete", status?}]` (`status` present on `complete` and `no_answer`) |
| `records/{id}.json` | `{id, status, people:int\|null, cant_leave_alone:[{who, need}], water_inside:bool\|null, can_help:{truck:bool, boat:bool, seats:int}, language, transcript:[{who:"agent"\|"resident", text}], house_card:str\|null, attempts:int}` |
| `queue.json` | `[{t_min, ranked:[{household_id, score, reasons:[str]}]}]` |
| `routes.json` | `[{vehicle_id, vehicle:"hwv"\|"boat"\|"neighbor_truck"\|"neighbor_boat", to_household_id, path:[[lon,lat]...], timestamps:[t_min...]}]` (deck.gl TripsLayer format) |
| `doorknock.geojson` | FeatureCollection of Polygons, `properties:{t_min, household_ids:[...]}` |
| `briefings.json` | `[{t_min, text}]` |
| `imagery.json` | `[{image_id, lon, lat, thumb:"img/<id>.jpg", verdict:"flooded"\|"not_flooded"\|"uncertain", explanation}]` (locations are approximate) |
| `results.json` | `{baseline_pct, swift_pct, record_accuracy, promise_violations, parallel_calls, n_households, mc:{median_baseline, median_swift, p10, p90, n, seconds}}` |
| `live_fallback.json` | `{record:<record for demo_household_id>, steps:[{delay_ms, who, text}]}` |
| `gpu_sample.json` | sample response of `/api/gpu` |

## Live endpoints (same origin when served from the GB10; `VITE_API_URL` in dev, empty = offline)
| Endpoint | Response |
|---|---|
| `POST /api/demo-call` | `{call_id}` — calls the demo phone for `demo_household_id` |
| `GET /api/live` | `{record:<record>\|null, call_status:"idle"\|"ringing"\|"in-progress"\|"completed"\|"no-answer"}` — poll every 2 s |
| `GET /api/gpu` | `{gpu_util, mem_used_gb, mem_total_gb, temp_c, llm_running}` — poll every 1 s |
| `POST /api/simulate-live` | `{started:true}` — starts background simulated calls on the GB10 (drives real GPU load during the demo) |

If any endpoint fails, the frontend must keep the demo running: the live-call scene plays `live_fallback.json`, the GB10 panel shows `gpu_sample.json`.
