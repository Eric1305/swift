# Swift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a flood threatens an area, an AI agent phones every household (Retell voice + Qwen on the GB10 as Retell's custom LLM), records who needs help, who can help and who never picked up, and shows it all on a dispatcher map. The demo is a scripted Harvey replay plus one live call to Eric's phone.

**Architecture:**
- **Python pipeline** precomputes the replay into static JSON/PNG "fixtures": flood depth, call timeline, records, routes, results.
- **React map app** plays those fixtures from a **Run Demo** button.
- **FastAPI agent server** on the GB10 is Retell's **custom LLM** over WebSocket. Retell handles phone lines, speech-to-text, turn-taking and voice; our server decides every reply. Code drives the conversation; Qwen only extracts facts and writes short acknowledgments.
- A live event would swap the pipeline's `--source replay` inputs for live ones (NWS alerts, gauge forecasts). Same outputs.

**Tech Stack:**
- Python 3.11 with uv **on the GB10**: fastapi, uvicorn, httpx, openai (vLLM client), pydantic, osmnx, networkx, py3dep, numpy, scipy, pillow, pytest.
- GPU on the GB10:
  - **CuPy** for the depth grid and the Monte Carlo replay, through an `xp` shim that falls back to numpy;
  - **nx-cugraph** as networkx's GPU backend for routing (`NX_CUGRAPH_AUTOCONFIG=True`), falling back to CPU networkx;
  - prefer the NGC RAPIDS container from the DGX Spark "CUDA-X Data Science" playbook if pip wheels fail on ARM64.
- Web: Vite + React + TS, maplibre-gl + deck.gl (`@deck.gl/react`, layers, geo-layers TripsLayer), CARTO dark-matter basemap (no key needed).
- GB10: vLLM serving `Qwen/Qwen3-VL-8B-Instruct` on :8000. cloudflared tunnel so Retell can reach the WebSocket and webhook. Retell: one agent (Custom LLM, English voice) + one Retell-purchased US number.

**Spec (inline; this file is the only artifact):**
- **Product:** call households in **order of predicted water arrival**. Retry non-answers at +2 and +5 min, then mark them ⚫ **no answer → door-knock list**. Silence never counts as safe.
- **Statuses:** `needs_help` 🔴, `can_help` 🟠 (truck/boat/seats), `safe` 🟢, `unconfirmed` 🟡, `no_answer` ⚫, `not_called` ⚪.
- **The agent never promises rescue.** Every sentence about help is a fixed template, and a guard blanks LLM text containing promise phrases.
- **LLM uses on the GB10:**
  1. per-turn fact extraction + acknowledgment;
  2. Qwen3-VL verdicts on the provided Harvey after-images (imagery check);
  3. responder house cards;
  4. commander briefings;
  5. LLM-simulated residents for the replay + extraction accuracy.
  Medical info stays on the box.
- **Map UI:** dark 3D map, depth overlay rising, buildings colored by status, call "arcs" fanning out, animated vehicle trips, door-knock clusters, a **Run Demo** button.
- **Live call:** goes to `DEMO_PHONE` (Eric's number) only. No judge input.
- **Budget:** 5 hours of coding, 2 people. Eric: backend/AI, Claude Max (parallel sessions). Teammate: frontend, Claude Pro (light usage), never blocked by Eric after minute 20.
- **No crediting of other projects anywhere.**

## Global Constraints
- The **5-hour clock**, scaled from the playbook's 24 h template. Mark each step's elapsed time in the chat:
  - 0:00–0:20 Architecture;
  - 0:20–1:15 Core pipeline (ugly end to end);
  - 1:15–3:15 Build sprint (two 1 h blocks);
  - **3:15 FEATURE FREEZE**;
  - 3:15–4:10 Integration and polish;
  - 4:10–4:35 Demo prep;
  - 4:35–5:00 Rehearse 3× and submit.
- **Checkpoints at 1:15, 2:15, 3:15:** "Can we demo right now?" If not, fix that before anything else.
- **Timebox:** any task more than 30 min over its box gets cut using the Cut List.
- **Tests are cut** to exactly: `tests/test_script.py`, `tests/test_schedule.py`, `tests/test_llm.py` (stubbed, no GB10 needed).
  - No frontend tests, no LLM-grader eval, no stress, load or integration suites.
  - Everything else is verified by the smoke command in its task.
- **Fixture directory:** `web/public/data/`. The frontend reads only from here plus the two live endpoints.
- **Environment variables** (agent server): `VLLM_BASE_URL` (default `http://localhost:8000/v1`), `VLLM_MODEL` (default `Qwen/Qwen3-VL-8B-Instruct`), `RETELL_API_KEY`, `RETELL_AGENT_ID`, `RETELL_FROM_NUMBER`, `DEMO_PHONE`, `PUBLIC_URL` (cloudflared URL), `DEMO_HOUSEHOLD_ID`. Never commit `.env`. Commit `.env.example`.
- **Frontend environment variable:** `VITE_API_URL` (empty → offline fallback).
- **Demo constants:** about 150 households; persona mix 20% needs_help / 15% can_help / 50% safe / 15% no_answer; seed `7`.
- **Depth model:** peak rise `12 ft`.
- **Vehicle limits:** car `0.5 ft`, `hwv` `3.0 ft`, boat any depth. Fleet: 2 `hwv` + 1 `boat` from a staging point at the highest-elevation household.
- **Retell setup (dashboard, before or at minute 0):**
  - Create an agent with **Response Engine = Custom LLM**, `llm_websocket_url = wss://<PUBLIC_URL host>/llm-websocket`, and webhook URL `https://<PUBLIC_URL host>/retell/webhook`.
  - Buy one US number and bind it to the agent.
  - Free tier: $10 credit and 20 concurrent calls, which covers the rehearsals plus the demo. Retell-purchased numbers call US numbers only.
  - **Re-point both URLs whenever the cloudflared URL changes.** A quick tunnel gets a new URL every restart, so keep the tunnel running all day.
  - `max_tokens` 150 per turn.
- **Where things run: everything on the GB10** (rubric: "use a large language model on the GB10", "use data on the GB10"):
  - vLLM :8000.
  - The agent server :8080, which **also serves the built dashboard** (`web/dist`) at `/`, with the API on the same origin.
  - The pipeline, the simulation, the imagery check and Monte Carlo, with GPU compute.
  - The repo and all of Eric's Claude Code sessions run **on the GB10** over NVIDIA Sync (VS Code Remote or SSH terminal); Claude Code supports ARM64 Linux.
  - The laptops are only screens and keyboards. The judges' view is `PUBLIC_URL` (one tunnel URL for Retell + dashboard), which also avoids venue Wi-Fi client isolation.
  - The teammate develops against fixtures locally with `npm run dev`, then pushes. The GB10 builds and serves `web/dist`.
- **GB10 visible in the demo:**
  - `GET /api/gpu` returns `nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits` + vLLM `/metrics` running-requests count.
  - The dashboard shows a live "GB10" panel: GPU %, memory, LLM calls in flight.
  - Run Demo starts the 150-household simulation **live on the GB10** while the replay plays, so the panel spikes for real.
- **The demo household:** `meta.json` carries `demo_household_id` (chosen by Task 1: a mid-arrival house near the center). The agent's `DEMO_HOUSEHOLD_ID` must equal it.

## Rubric re-run (GB10-first)
| Criterion | What judges see | Where it lives on the GB10 |
|---|---|---|
| Creativity | Calls in **water-arrival order**, neighbor trucks/boats, depth-limited routing, door-knock list, flood map checked against the images | All of it computed on the GB10 |
| Social impact | Harvey numbers + the "how it works in a real event" table | n/a |
| **LLM on the GB10** | A real phone call whose every reply is decided by **Qwen on the GB10** (Retell only does voice); 150 simulated calls running in parallel; Qwen3-VL imagery verdicts; house cards; commander briefings; **live GB10 panel** showing LLM calls in flight | vLLM :8000 |
| **Data on the GB10** | GPU depth grid from the 3DEP DEM + provided rainfall database; GPU routing (nx-cugraph); **1,000-night GPU Monte Carlo** giving a p10–p90 range, not one number; provided Harvey images through Qwen3-VL | CuPy / nx-cugraph / vLLM |
| Interface | Dark 3D map, Run Demo, the phone rings live, GB10 panel spikes as the system works | Served by the GB10 at `PUBLIC_URL` |

Remaining laptop use: screens and the teammate's local `npm run dev` before integration. Nothing in the final demo runs off the GB10 except Retell's voice layer.

## Grill findings (checked against docs, 2026-11-13)
| # | Assumption | Finding | Change |
|---|---|---|---|
| 1 | Retell can use our own model | [Custom LLM: Retell opens a WebSocket per call to `llm_websocket_url/{call_id}`; it handles telephony, speech-to-text, turn-taking and voice](https://docs.retellai.com/integrate-llm/overview) | Qwen stays on the GB10, which preserves the rubric's "LLM on GB10" |
| 2 | Message shapes | [config event, then the begin message; reply `{response_type:"response", response_id, content, content_complete, end_call}`; a message missing `response_type` is treated as a response](https://docs.retellai.com/api-references/llm-websocket) | Task 6 uses those exact shapes; the agent speaks first via the begin message |
| 3 | Detecting no-answer | `call_ended` still fires for unconnected calls; `disconnection_reason` is `dial_no_answer`/`dial_busy`/`dial_failed`; a declined call can show as `dial_no_answer` ([Retell webhook docs](https://docs.retellai.com/features/webhook-overview), [community](https://community.retellai.com/t/why-does-retell-map-declined-calls-to-dial-no-answer/275)) | Map all of those + `voicemail_reached` → ⚫ |
| 3b | Outbound call API | [`POST /v2/create-phone-call` with `from_number`, `to_number`, `override_agent_id`, `metadata`](https://docs.retellai.com/api-references/create-phone-call); Retell numbers call the US only | `/api/demo-call` uses it; `DEMO_PHONE` is a US number |
| 4 | Parse JSON from free text | [vLLM supports `response_format={"type":"json_schema",...}`](https://docs.vllm.ai/en/latest/features/structured_outputs.html); `guided_json` was removed in v0.12 | `extract` sends a per-step JSON schema; keep the parse fallback in case the container's vLLM is old |
| 5 | osmnx v1 call style | [v2: `ox.graph.graph_from_bbox(bbox=(left,bottom,right,top), network_type=...)`, `ox.features.features_from_bbox(bbox, tags)`; keyword-only args](https://osmnx.readthedocs.io/en/stable/user-reference.html) | Task 1 uses the v2 signatures; pin `osmnx>=2` |
| 6 | TripsLayer timestamps in ms | [Units only need to match `currentTime` and `trailLength`; float32 precision](https://deck.gl/docs/api-reference/geo-layers/trips-layer) | Use **minutes since start** everywhere (`timestamps`, `currentTime`); `trailLength` 20 |
| 7 | Harvey images have coordinates | The `image_metadata.csv` columns (from `texas_flood.py`) show only locality, with no lat/lon | Use the fixed Bear Creek bbox; place imagery pins at locality centroids; label them "approx. location" |
| 8 | Laptop can reach the GB10 directly | Venue Wi-Fi often isolates clients | All live traffic goes through `PUBLIC_URL` |
| 9 | The live house exists on the map | It wasn't guaranteed before | `demo_household_id` goes in `meta.json` (Task 1) and is shared with the agent env |
| 10 | Depth rolling minimum | Needs a fast filter on the 10 m DEM | `scipy.ndimage.minimum_filter(size=101)`; add the `scipy` dependency |

## Review Focus
1. Retell sends `reminder_required` or an empty user turn (caller silent or noisy) → re-ask once, then advance, never crash. → `test_script.py::test_empty_reply_reasks_once`
2. A caller corrects an earlier answer ("no wait, it's three of us") → the latest value wins. But `cant_leave_alone` entries, once recorded, are never dropped. → `test_script.py::test_correction_keeps_cant_leave`
3. Qwen returns non-JSON or wrong keys → treat it as no fields extracted; the call continues. → `test_llm.py::test_bad_json_returns_empty_fields`
4. The LLM acknowledgment contains a promise ("help is on the way", "we're sending someone", "estamos enviando") → blanked. → `test_script.py::test_guard_blanks_promises`
5. The agent server or tunnel is unreachable during the demo → the frontend plays `live_fallback.json` and the demo still finishes. → manual check in Task 9 Step 3.

---

## Data contract (Task 0 writes this as `CONTRACT.md`; it's the only shared dependency)
| File | Shape |
|---|---|
| `meta.json` | `{demo_household_id, center:[lon,lat], zoom, pitch, bearing, timeline:{start_iso, end_min, step_min}, staging:[lon,lat], hub:[lon,lat], depth_stages:[{t_min, png, bounds:[[w,s],[e,n]]}]}` |
| `households.geojson` | Polygon (footprint) features, `properties:{id, address, water_arrival_min, depth_ft_peak, height_m}` |
| `timeline.json` | `[{t_min, household_id, event:"call_start"\|"no_answer"\|"retry"\|"complete", status?}]` |
| `records/{id}.json` | `{id, status, people:int\|null, cant_leave_alone:[{who, need}], water_inside:bool\|null, can_help:{truck:bool, boat:bool, seats:int}, language, transcript:[{who:"agent"\|"resident", text}], house_card:str\|null, attempts:int}` |
| `queue.json` | `[{t_min, ranked:[{household_id, score, reasons:[str]}]}]` |
| `routes.json` | `[{vehicle_id, vehicle:"hwv"\|"boat"\|"neighbor_truck"\|"neighbor_boat", to_household_id, path:[[lon,lat]...], timestamps:[t_min...]}]` (TripsLayer format) |
| `doorknock.geojson` | Polygon features `properties:{t_min, household_ids:[...]}` |
| `briefings.json` | `[{t_min, text}]` |
| `imagery.json` | `[{image_id, lon, lat, thumb:"img/<id>.jpg", verdict:"flooded"\|"not_flooded"\|"uncertain", explanation}]` |
| `results.json` | `{baseline_pct, swift_pct, record_accuracy, promise_violations, parallel_calls, n_households}` |
| `live_fallback.json` | a complete record for `DEMO_HOUSEHOLD_ID` + `steps:[{delay_ms, transcript_line}]` |

**Live endpoints:**
- `POST {VITE_API_URL}/api/demo-call` → `{call_id}`
- `GET {VITE_API_URL}/api/live` → `{record: <record>|null, call_status:"idle"|"ringing"|"in-progress"|"completed"|"no-answer"}`, polled every 2 s.
- `GET {VITE_API_URL}/api/gpu` → `{gpu_util, mem_used_gb, mem_total_gb, temp_c, llm_running}`, polled every 1 s (sample fixture: `gpu_sample.json`).
- `POST {VITE_API_URL}/api/simulate-live` → `{started:true}`. Runs `simulate_all` in the background into `/tmp/hg_live/`, never overwriting fixtures. Purely to drive real GB10 load during the demo.

## File structure
```
swift/
  CONTRACT.md  README.md  .env.example  pyproject.toml
  pipeline/  area.py depth.py schedule.py dispatch.py baseline.py build.py live_alerts.py(stretch)
  agent/     script.py llm.py server.py content.py simulate.py
  tests/     test_script.py test_schedule.py test_llm.py
  web/       (teammate-owned) src/{App.tsx, map/*.tsx, panels/*.tsx, demo/*.ts}  public/data/*
```

## Parallel lanes
- **Eric** runs three Claude Code sessions in separate git worktrees after Task 0: **Lane A** (Tasks 1, 5), **Lane B** (Tasks 2, 6), **Lane C** (Tasks 3, 7). Eric reviews and merges at each checkpoint.
  - Lane A needs no model, but runs on the GB10 for GPU compute (CuPy, nx-cugraph).
  - Lanes B and C need vLLM running.
  - Lane C imports `agent.script` and `agent.llm` from Lane B. Until B merges at 1:15, Lane C uses the interfaces below with a stub.
- **The teammate** runs Tasks T1–T6 against the sample fixtures only.

---

### Task 0 (Eric, 0:00–0:20): Repo, contract, sample fixtures, GB10 + Retell up
**Files:** Create `CONTRACT.md`, `.env.example`, `pyproject.toml`, `web/public/data/*` (samples: 5 households, 1 depth stage PNG, 20 timeline events, 5 records, 1 route, 1 briefing, 2 imagery items, results, live_fallback).
- [ ] **Step 1:** `gh repo create swift --private --clone`. Write `CONTRACT.md` from the table above. Write the samples **by hand or with Claude** in the exact shapes. Push. *Tell the teammate to start T1.*
- [ ] **Step 2:** On the GB10 (NVIDIA Sync terminal), run the workbook's `docker run ... --model Qwen/Qwen3-VL-8B-Instruct --max-model-len 8192`. Verify with `curl $VLLM_BASE_URL/models`: it lists the model.
- [ ] **Step 3:** On the GB10, install cloudflared (arm64 .deb) and run `cloudflared tunnel --url http://localhost:8080`; save the URL as `PUBLIC_URL`. In the Retell dashboard, create the Custom LLM agent with the WebSocket and webhook URLs pointing at `PUBLIC_URL`, buy a US number, bind it, and copy the API key, agent ID and number into `.env`. Check: `curl -H "Authorization: Bearer $RETELL_API_KEY" https://api.retellai.com/list-agents` lists the agent. (The phone only rings once Task 6 serves the WebSocket.)
- [ ] **Step 4:** Commit: `git commit -m "chore: contract, sample fixtures, env template"`.

### Task 1 (Lane A, 0:20–1:15): Area, depth, households → real `meta/households/depth`
**Files:** Create `pipeline/area.py`, `pipeline/depth.py`, `pipeline/build.py`.
**Interfaces:**
- Produces: `load_area(bbox: tuple[float,float,float,float], cache: Path) -> Area`, where `Area` holds `households: GeoDataFrame` (id, address, geometry, height_m), `graph: nx.MultiDiGraph`, `dem: xarray.DataArray`.
- Produces: `rise_curve(source: str) -> list[tuple[int, float]]` returning (t_min, rise_ft).
- Produces: `household_depths(area, curve) -> DataFrame[id, water_arrival_min, depth_ft_peak]`.
- Produces: `write_depth_stages(area, curve, out: Path) -> list[dict]`.
- Produces: `python -m pipeline.build --source replay --stage base --out web/public/data` (stage `base` = area/depth/households; stage `dispatch` = Task 5 outputs, which need the `records/` from Task 7).
- [ ] **Step 1:** Bbox `(-95.67,29.80,-95.62,29.84)` (Bear Creek, west Houston; the metadata has no coordinates, see Grill #7). `ox.features.features_from_bbox(bbox, {"building": True})` → sample 150 with seed 7 (address = `addr:*` tags or `"<n> <nearest street name>"`); drive graph via `ox.graph.graph_from_bbox(bbox=bbox, network_type="drive")`; 3DEP 10 m DEM via `py3dep.get_dem(bbox, 10)`. Choose `demo_household_id` (median arrival, nearest the center) and write it to `meta.json`. Cache to `pipeline/cache/`.
- [ ] **Step 2: Depth model.**
  - `hand_ft = (dem - minimum_filter(dem, size=101)) * 3.281`, using `cupyx.scipy.ndimage.minimum_filter` on the GB10 GPU (the `xp` shim falls back to `scipy.ndimage`). All depth stages are computed as one GPU array op over time × grid.
  - `depth_ft(t) = max(0, rise_ft(t) - hand_ft)`.
  - `rise_ft(t) = 12 * cumrain(t)/cumrain_total`, where cumrain comes from `observations.sqlite` via the datathon's `load_rainfall("TX001_2017_NOAA", 14)`. If that file is missing, use a fixed logistic curve over 0–360 min.
  - `water_arrival_min` = first t where the household's depth > 0.5 ft (else null).
  - Stages every 30 min, rendered as blue RGBA PNGs with alpha ∝ depth.
- [ ] **Step 3: Smoke.** `uv run python -m pipeline.build --source replay --stage base --out web/public/data` writes `meta.json`, `households.geojson` and 13 stage PNGs. Open one PNG: low areas are blue.
- [ ] **Step 4:** Commit `feat(pipeline): area, depth, households`.

### Task 2 (Lane B, 0:20–1:15): Conversation script, guard, LLM extraction
**Files:** Create `agent/script.py`, `agent/llm.py`, `tests/test_script.py`, `tests/test_llm.py`.
**Interfaces:**
- Produces in `agent/script.py`:
  - `STEPS = ["confirm_address","people","cant_leave","water_inside","can_help","readback","close"]`;
  - `class Record(BaseModel)` with the contract record fields;
  - `class CallState(BaseModel): record: Record; step: str; reasked: bool = False`;
  - `prompt_for(state: CallState) -> str` (code-written question; readback/close built from templates);
  - `advance(state: CallState, fields: dict, ack: str) -> tuple[CallState, str]` (returns the new state and the text to speak: `guard(ack) + " " + prompt_for(next)`);
  - `status_of(rec: Record) -> str`;
  - `guard(text: str) -> str`;
  - `BANNED = ["help is on the way","on their way","we're sending","we are sending","someone is coming","you'll be rescued","you are safe","you're safe","estamos enviando","ya van","está a salvo"]`;
  - `TEMPLATES` with keys `needs_help`, `can_help`, `safe`, `unconfirmed`. `needs_help` = "I've recorded that you need help leaving. No responder has been assigned yet. If water is rising inside, move to the highest floor and call 911 if you can get through."
- Produces in `agent/llm.py`: `extract(step: str, utterance: str) -> tuple[dict, str]`, returning (fields, ack); `ask(prompt: str, image_path: str | None = None, max_tokens: int = 300) -> str`. Both use the OpenAI client against `VLLM_BASE_URL` with `temperature=0` and `extra_body={"chat_template_kwargs":{"enable_thinking":False}}`.
- [ ] **Step 1: Write the tests.**
  - `test_guard_blanks_promises`: `guard("Okay, help is on the way!") == ""`, `guard("Got it, thank you.") == "Got it, thank you."`.
  - `test_empty_reply_reasks_once`: an empty `fields` and `ack` at step `people` → the same step with `reasked=True`; a second empty → the step becomes `cant_leave`.
  - `test_correction_keeps_cant_leave`: apply `{"people":2,"cant_leave_alone":[{"who":"mother","need":"power wheelchair"}]}`, then `{"people":3}` → `people==3` and `len(cant_leave_alone)==1`.
  - `test_status_rules`: cant_leave non-empty or `water_inside` → `needs_help`; else truck/boat/seats>0 → `can_help`; people known → `safe`; else `unconfirmed`.
  - `test_bad_json_returns_empty_fields` (`tests/test_llm.py`): monkeypatch the client to return `"sure! here you go"` → `extract(...) == ({}, "")`.
- [ ] **Step 2:** `uv run pytest tests/test_script.py tests/test_llm.py -v` fails (missing modules).
- [ ] **Step 3:** Implement. `extract` passes `response_format={"type":"json_schema","json_schema":{"name":step,"schema":STEP_SCHEMAS[step]}}`, with only that step's keys plus `ack` (≤12 words, no promises). Still parse defensively (`json.loads` on the first `{...}` match; on any error return `({}, "")`), since the container's vLLM version is unknown.
- [ ] **Step 4:** Tests pass. Live check: `uv run python -c "from agent.llm import extract; print(extract('cant_leave','my mom uses a power wheelchair'))"` returns cant_leave_alone with a power wheelchair.
- [ ] **Step 5:** Commit `feat(agent): code-driven call script, promise guard, extraction`.

### Task 3 (Lane C, 0:20–1:15): Imagery check
**Files:** Create `agent/content.py` (imagery part).
**Interfaces:**
- Consumes: `agent.llm.ask`.
- Produces: `imagery_check(image_ids: list[str], out: Path) -> list[dict]` (contract `imagery.json`; copies 512 px thumbs to `out/img/`).
- [ ] **Step 1:** For each `*_2017_NOAA` image in `image_metadata.csv`, ask: `"Is floodwater visibly covering roads or land around houses? Reply JSON {\"verdict\":\"flooded|not_flooded|uncertain\",\"explanation\":\"<=20 words\"}"`. Locate it by metadata coordinates, or else by locality centroid.
- [ ] **Step 2: Smoke.** `uv run python -c "from agent.content import imagery_check; ..."` writes `imagery.json` with at least 6 items, most of them `flooded`.
- [ ] **Step 3:** Commit `feat(content): Qwen3-VL imagery check of Harvey after-images`.

**CHECKPOINT 1:15:** merge A, B and C into main. Can we demo? Map shows real households + depth (teammate pulls the data), and `extract` works live. If not, fix only that.

### Task 5 (Lane A, 1:15–2:45): Call timeline, rescue queue, routes, door-knock, baseline
**Files:** Create `pipeline/schedule.py`, `pipeline/dispatch.py`, `pipeline/baseline.py`, `tests/test_schedule.py`; modify `pipeline/build.py`.
**Interfaces:**
- Consumes: `household_depths(...)`, the records from Task 7 (`records/{id}.json`), and `Record`/`status_of` from `agent.script`.
- Produces:
  - `build_timeline(depths: DataFrame, answers: dict[str,bool], parallel: int = 20, call_min: float = 3.0) -> list[dict]`;
  - `rank(records: list[Record], depths) -> list[dict]` (score = 100·cant_leave + 50·water_inside + 10·depth_ft_peak − 0.1·water_arrival_min);
  - `routes(area, ranked, records, depths) -> list[dict]`;
  - `doorknock(area, no_answer_ids) -> FeatureCollection`;
  - `compare(depths, records, routes_fn) -> dict`.
- [ ] **Step 1: Write the tests.**
  - `test_no_answer_retries_then_marks`: a household with `answers[id]=False` gets events `call_start@t`, `retry@t+2`, `retry@t+5`, then `no_answer` with `status:"no_answer"`.
  - `test_call_order_follows_arrival`: the first `call_start` belongs to the household with the smallest `water_arrival_min`; never more than `parallel` calls active at once.
- [ ] **Step 2:** `uv run pytest tests/test_schedule.py -v` fails.
- [ ] **Step 3: Implement.**
  - **Routing:** shortest path on the drive graph from `staging`. Block edges for a vehicle at time t when the edge's depth exceeds its limit (`hwv` 3.0 ft; `neighbor_truck` 3.0; boats ignore limits). Assign greedily in rank order to the vehicle that would arrive earliest. Timestamps come from edge length / 25 mph (boats 8 mph) + 10 min boarding.
  - **Door-knock:** cluster no-answer households within 300 m (convex hull).
  - **Baseline:** 55% of needs_help households "reach 911" at arrival − 20 min; first come first served; same fleet.
  - **Swift:** every needs_help known at call completion; served in rank order.
  - `pct` = share picked up before `water_arrival_min`.
  - **GPU Monte Carlo on the GB10:** `monte_carlo(depths, records, n=1000) -> dict` reruns baseline vs. Swift over 1,000 randomized flood nights in a vectorized `xp` (CuPy) array: peak rise 8–16 ft, no-answer rate 5–30%, fleet 2–5 vehicles, 911 reach rate 30–70%. It writes `results.json` with the `mc:{median_baseline, median_swift, p10, p90, n, seconds}` field and prints the CuPy vs. numpy runtime for the README.
  - **Routing on GPU:** `NX_CUGRAPH_AUTOCONFIG=True` before importing networkx; log which backend ran.
- [ ] **Step 4:** Tests pass. Until Task 7 lands, stub `records/` from sample fixtures. Then `uv run python -m pipeline.build --source replay --stage dispatch --out web/public/data` writes `timeline.json`, `queue.json`, `routes.json`, `doorknock.geojson`, `results.json` (baseline/swift + `mc` filled).
- [ ] **Step 5:** Commit `feat(pipeline): call schedule, rescue ranking, depth-aware routes, baseline`.

### Task 6 (Lane B, 1:15–2:45): Retell custom-LLM call server
**Files:** Create `agent/server.py`.
**Interfaces:**
- Consumes: `agent.script.*`, `agent.llm.extract`, `agent.content.house_card` (Task 7).
- Produces: FastAPI app `agent.server:app` on :8080 with:
  - `POST /api/demo-call`: `POST https://api.retellai.com/v2/create-phone-call` (header `Authorization: Bearer $RETELL_API_KEY`), body `{from_number: RETELL_FROM_NUMBER, to_number: DEMO_PHONE, override_agent_id: RETELL_AGENT_ID, metadata: {household_id: DEMO_HOUSEHOLD_ID}}` → returns `{call_id}`.
  - `WS /llm-websocket/{call_id}` (Retell connects here, through `wss://PUBLIC_URL/llm-websocket`). **On connect:**
    - send `{"response_type":"config","config":{"auto_reconnect":true,"call_details":true}}`;
    - then the begin message `{"response_type":"response","response_id":0,"content":<intro + prompt_for(confirm_address)>,"content_complete":true}`. On outbound calls the agent speaks first. The intro is "This is Swift, an automated flood assistant working with local emergency services."
  - **On each event:**
    - `ping_pong` → echo it.
    - `update_only` → set `call_status="in-progress"`.
    - `response_required` → take the last `transcript` item with `role=="user"` → `extract` → `advance`. Reply with `{response_type:"response", response_id:<same>, content:<text>, content_complete:true}`, adding `"end_call":true` once the state reaches `close` (and write the house card).
    - `reminder_required` → treat it as an empty reply (`advance(state, {}, "")`), which gives the re-ask-once behavior.
    - Always answer with the **latest** `response_id`; drop work for stale ids.
  - `POST /retell/webhook`: `event=="call_ended"`. If `call.disconnection_reason` is in `{"dial_no_answer","dial_busy","dial_failed","voicemail_reached"}` → `status="no_answer"`, `attempts+=1`, `call_status="no-answer"`; else `call_status="completed"`.
  - `GET /api/live`.
  - `GET /api/gpu` (shells out to `nvidia-smi --query-gpu=... --format=csv,noheader,nounits`; `llm_running` parsed from `GET VLLM /metrics` `vllm:num_requests_running`; on any error return zeros).
  - `POST /api/simulate-live` (spawns `agent.simulate.simulate_all(households, Path("/tmp/hg_live"))` in a background task; ignores repeat calls while one is running).
  - Mount `web/dist` with `StaticFiles(html=True)` at `/`, **after** the API routes.
  - CORS allows all origins.
  - In-memory `CallState` keyed by call_id, seeded with the `DEMO_HOUSEHOLD_ID` household's address.
- [ ] **Step 1:** Implement with FastAPI `WebSocket` + `httpx`, without the Retell SDK. Keep each reply as one complete chunk (no streaming) to stay simple.
- [ ] **Step 2: Smoke.** `uv run uvicorn agent.server:app --port 8080`, then `curl -X POST localhost:8080/api/demo-call`. Eric's phone rings and the agent speaks first. Answer with the rehearsal script (Task 10). `curl localhost:8080/api/live` shows `status:"needs_help"`, `cant_leave_alone:[{who:"mom", need:"power wheelchair"}]`, and a non-empty house card. **The gap after you stop talking is under about 2 s.** If not, lower `max_tokens` to 80 and shorten the extract prompt.
- [ ] **Step 3: Smoke.** Decline the call → the `call_ended` webhook arrives → `/api/live` shows `call_status:"no-answer"` and `status:"no_answer"`.
- [ ] **Step 4:** Commit `feat(agent): Retell custom-LLM call loop on GB10`.

### Task 7 (Lane C, 1:15–2:45): Simulated residents, house cards, briefings, accuracy
**Files:** Modify `agent/content.py`; create `agent/simulate.py`.
**Interfaces:**
- Consumes: `agent.script.{CallState, Record, prompt_for, advance, status_of, guard}`, `agent.llm.{extract, ask}`.
- Produces:
  - `house_card(rec: Record) -> str` (≤40 words: people, who can't leave and why, power chair weight note if any, language, water inside);
  - `briefing(t_min: int, records: list[Record], ranked: list[dict]) -> str` (≤60 words);
  - `simulate_all(households: GeoDataFrame, out: Path, concurrency: int = 32) -> dict` (writes `records/*.json`; returns `{record_accuracy, promise_violations, parallel_calls, answers: dict[id,bool]}`).
- [ ] **Step 1: Personas.** Seed 7, with the mix from Global Constraints. Each persona is a ground-truth dict and a speaking style (plain, rambling, corrects themselves, 10% Spanish). A resident LLM turn answers `prompt_for(state)` in character (`ask`, max 60 tokens). Run the same `extract` → `advance` loop as the live call; asyncio with `concurrency` parallel calls.
- [ ] **Step 2: Accuracy.** `record_accuracy` = share of personas whose `status_of(record)` equals the ground-truth status. `promise_violations` = count of agent acknowledgments that `guard` blanked. Then house cards for needs_help records, and briefings at t = 60, 180, 300.
- [ ] **Step 3: Smoke.** `uv run python -m agent.simulate --out web/public/data` writes about 130 records + `briefings.json` and prints accuracy (target ≥ 0.85) and the parallel count. **Show this run on the DGX Dashboard and screenshot it for the README.**
- [ ] **Step 4:** Commit `feat(content): simulated residents, house cards, briefings, accuracy`.

**CHECKPOINT 2:15:** can we demo? Real records render in the teammate's drawer, and a live call works. **CHECKPOINT 3:15 = FEATURE FREEZE:** after this, only fix demo-breaking bugs.

### Task 8 (Eric, 2:45–3:15 if on time; else cut): Live Texas alerts toggle (stretch)
**Files:** Create `pipeline/live_alerts.py`.
- [ ] **Step 1:** `fetch_alerts() -> FeatureCollection` from `https://api.weather.gov/alerts/active?area=TX&event=Flash%20Flood%20Warning,Flood%20Warning` (User-Agent header) → `web/public/data/live_alerts.geojson` (may be empty, which is fine). Smoke: the file is written. Commit.

### Task 9 (Eric + teammate, 3:15–4:10): Integration and polish
- [ ] **Step 1:** Eric runs `pipeline.build --stage base` → `agent.simulate` → `pipeline.build --stage dispatch` for the final fixtures and commits `web/public/data`. Teammate pulls and sets `VITE_API_URL=$PUBLIC_URL`.
- [ ] **Step 2:** Full Run Demo with a live call. Fix only what breaks the demo.
- [ ] **Step 3:** Stop the agent server and run the demo again: the live scene plays `live_fallback.json` and the demo finishes (Review Focus #5).
- [ ] **Step 4:** Commit `chore: final fixtures, integration fixes`.

### Task 10 (Eric, 4:10–5:00): Demo prep, rehearse, submit
- [ ] **Step 1: README.**
  - Problem stats with sources: Harvey 911 about 56k calls in under 24 h; fewer than 5% of the disability registry contacted; 58–63% of flood deaths in vehicles; request rates uncorrelated with FEMA zones.
  - Architecture; the honesty rule; results; the "how it works in a real event" table; run steps; DGX screenshot.
- [ ] **Step 2:** Record the backup video of the full Run Demo with a live call.
- [ ] **Step 3: Rehearse 3× and time it.** Eric's scripted answers on the call:
  - address → "Yes, that's right"; people → "Two, me and my mom";
  - can't leave → "My mom uses a power wheelchair";
  - water inside → "It's at the front step, not inside yet";
  - can help → "No";
  - readback → "Yes".
- [ ] **Step 4:** `gh repo edit --visibility public --accept-visibility-change-consequences`; submit the link early; stop touching code.

---

## Teammate tasks (frontend, Claude Pro; fixtures only, never wait on Eric)
Tips for saving Claude usage: paste `CONTRACT.md` into one session, ask for one component at a time, and hand-write the styling and wiring. Each task is checked by eye in `npm run dev`.

- **T1 (0:20–0:50) Scaffold.**
  - `npm create vite@latest web -- --template react-ts`; install `maplibre-gl react-map-gl @deck.gl/react @deck.gl/layers @deck.gl/geo-layers`.
  - Layout: full-screen map; top bar (title "Swift", clock, **Run Demo** button, speed 1×/5×/20×); left panel (counters + rescue queue + briefing card); right drawer (household detail); bottom-right results card (hidden until the end).
  - Dark theme. Status colors: needs_help `#ef4444`, can_help `#f59e0b`, safe `#22c55e`, unconfirmed `#eab308`, no_answer `#111827` with a white outline, not_called `#6b7280`.
  - Check: the page loads the sample `meta.json` and centers the map with pitch 50.
- **T2 (0:50–1:45) Map layers** (`<DeckGL>` wrapping `<Map>` from `react-map-gl/maplibre`, `mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"`; all times in **minutes since start**):
  - `BitmapLayer` of the depth stage for the current t (crossfade between stages);
  - `PolygonLayer` of household footprints, **extruded** by `height_m`, colored by status at t;
  - `ArcLayer` from `hub` to houses with an active `call_start` (pulsing);
  - `TripsLayer` for `routes.json` (`currentTime` = clock minutes, `trailLength` 20, colored by vehicle);
  - `PolygonLayer` door-knock clusters (dashed white);
  - `IconLayer` imagery pins with a popup (thumb + verdict + explanation).
  - Check: every layer renders from the samples.
- **T3 (1:45–2:30) Timeline engine** (`src/demo/timeline.ts`):
  - `statusAt(t)` folds `timeline.json` events (call_start → "calling", complete → record status, no_answer → `no_answer`);
  - a clock with play/pause/speed; counters (called / needs help / can help / safe / no answer);
  - a queue list from `queue.json` at t (click → fly to the house);
  - a briefing card showing the latest `briefings.json` entry ≤ t.
  - Check: scrubbing the clock changes colors and counters.
- **T4 (2:30–3:15) Household drawer + Run Demo director** (`src/demo/director.ts`). The drawer shows chat-bubble transcript, record fields, house card and attempts. The Run Demo button runs a fixed scene list:
  1. 0 s: fly in from a high view to the area, water at stage 0;
  2. 5 s: play at 20×: water rises, call arcs fan out, houses change color;
  3. 25 s: pause, auto-open the top-ranked red house's drawer;
  4. 35 s: resume at 20×: trips animate, door-knock clusters appear, briefing updates;
  5. 55 s: show the imagery pins with one popup open;
  6. 65 s: **Live call scene**: highlight `DEMO_HOUSEHOLD_ID`, POST `/api/demo-call`, poll `/api/live` every 2 s, stream the transcript into the drawer and recolor the house when the status arrives. If the API fails or 90 s pass, play `live_fallback.json` steps;
  7. end: slide in the results card (baseline % vs. Swift %, the 1,000-night Monte Carlo range p10–p90, accuracy, 0 promise violations, parallel calls).
  - From scene 2 onward, the **GB10 panel** (top right) polls `/api/gpu` every 1 s. Scene 2 also POSTs `/api/simulate-live` so the GPU and LLM-in-flight numbers climb during the replay.
  - Check: Run Demo plays end to end on the samples with `VITE_API_URL` empty.
- **T5 (3:15–4:10) Integrate + polish:** add the **GB10 panel** (GPU % sparkline, memory bar, "LLM calls in flight", from `/api/gpu`; sample: `{gpu_util, mem_used_gb, mem_total_gb, temp_c, llm_running}`); pull the real fixtures; build with `VITE_API_URL=` (same origin) so the GB10 serves it; fix layout overlaps; smooth camera moves; legend; screenshots for the README.
- **T6 (4:10–5:00):** rehearse with Eric; keep a second browser tab ready with `VITE_API_URL` empty as a fallback.

## Cut List (cut in this order when a timebox overruns)
1. Task 8 live alerts.
2. Spanish personas.
3. Imagery IconLayer popups (keep the pins only).
4. Neighbor vehicles in routing (agency fleet only).
5. Commander briefings (show a static one).
6. TripsLayer animation (static route lines).
7. Simulated LLM residents (scripted persona answers instead).

**Never cut:** Run Demo, the live call to `DEMO_PHONE` with its fallback, households colored by status, results card.

## Verification (whole project)
- `uv run pytest -q`: 7 tests pass.
- `uv run python -m pipeline.build --source replay --stage base --out web/public/data && uv run python -m agent.simulate --out web/public/data && uv run python -m pipeline.build --source replay --stage dispatch --out web/public/data`: every contract file present; accuracy ≥ 0.85; promise_violations printed.
- On the GB10: `cd web && npm run build`, then `uv run uvicorn agent.server:app --port 8080` serves the dashboard at `PUBLIC_URL/`. Run Demo completes in about 100 s, the GB10 panel shows GPU activity, Eric's phone rings and the house turns red with a house card.
- With the agent server off, Run Demo still completes using `live_fallback.json`.
- Repo public, link submitted before the deadline.
