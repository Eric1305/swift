# Swift: how it works (plain-English technical overview)

## In one paragraph
When a flood is coming, the people most likely to die are the ones who can't leave on their own, and in a big disaster
911 is jammed. **Swift flips it: instead of waiting for people to get through to 911, an AI agent phones every household,
in the order the water is predicted to reach them.** It asks a few short questions, writes down who needs help leaving,
who can help (a truck, a boat, free seats), who is fine, and who never picked up. A dispatcher sees all of it on one map,
with rescue routes that avoid streets too deep for each vehicle and a door-knock list for the silent homes.

## The big picture
```text
                         PRECOMPUTED (before the demo)                                LIVE (during the demo)
 ┌───────────────────────────────────────────────────────────┐        ┌───────────────────────────────────────────┐
 │ Hugging Face flood dataset ─┐                              │        │ Your phone                                 │
 │ OpenStreetMap homes/roads ──┼─▶ pipeline/ (flood depth,    │        │   ▲ voice                                  │
 │ USGS elevation (3DEP) ──────┘    call order, routes)       │        │   ▼                                        │
 │                     │                                     │        │ Retell (phone line + speech↔text)          │
 │                     ▼                                     │        │   ▲ text over WebSocket                    │
 │ agent/simulate.py: 150 "calls" to simulated residents ────┼──┐     │   ▼                                        │
 │                     │                                     │  │     │ Render relay (public URL in the cloud)     │
 │                     ▼                                     │  │     │   ▲ one outbound WebSocket from laptop     │
 │ web/public/data/  (JSON + images the dashboard plays)     │  │     │   ▼                                        │
 └───────────────────────────────────────────────────────────┘  │     │ Our server (agent/server.py, laptop :8080) │
                                                                │     │   ▲ JSON request/response                  │
                         ┌──────────────────────────────────────┘     │   ▼                                        │
                         ▼                                            │ Qwen3-VL-8B on the organizers' GB10 server │
                 Qwen3-VL-8B on the GB10  ◀───────────────────────────┘                                            │
                                                                      └───────────────────────────────────────────┘
 Dashboard (React map at localhost:8080) plays the precomputed files and, in scene 6, shows the live call as it happens.
```

There are **two halves**:
- **Precomputed replay (Hurricane Harvey, Bear Creek, 150 homes).** Built ahead of time so the demo is fast and works offline.
- **One live phone call** to the presenter's phone, which runs through the exact same call code as the 150 simulated calls.

## What each part is
| Part | What it is | What it does |
|---|---|---|
| **Qwen3-VL-8B** | An 8-billion-parameter vision-language model (reads text *and* images), served by the organizers on a Dell Pro Max GB10 at `http://10.246.100.230/v1` (OpenAI-compatible API, model `qwen3-vl-8b-instruct`, event key) | Every AI step in Swift. See "What Qwen does" |
| **Retell** | A voice-call platform | Owns the phone number, dials, turns speech into text and text into a voice. **It does not decide what to say.** We use its "Custom LLM" mode, so it asks our server for every line |
| **Render relay** | A tiny public web app (`relay/app.py`) on Render's cloud | The venue Wi-Fi blocks incoming connections to the laptop. So the laptop opens **one outbound** connection to the relay, and the relay passes Retell's messages through it |
| **Our server** | FastAPI app, `agent/server.py`, on the laptop | Runs the call script, calls Qwen, keeps the household record, serves the dashboard and its live API |
| **Call script** | `agent/script.py` (plain Python) | Decides *which question comes next*, when to re-ask, when to read back and how to end. Holds the honesty rules |
| **Pipeline** | `pipeline/` (Python + NumPy) | Flood-depth model, call order, rescue ranking, routes, door-knock clusters, baseline comparison and Monte Carlo |
| **Dashboard** | React + deck.gl/MapLibre in `web/` | The 3D map, Run Demo, transcripts, results |

## What Qwen does (and doesn't)
Qwen has **five jobs**. Each one is a single request with a short prompt, and the answer comes back in about 0.3–0.4 s.

| # | Job | Input to Qwen | Output from Qwen | Where |
|---|---|---|---|---|
| 1 | **Understand each answer on a call** | The question we asked + what the resident just said | Strict JSON with the facts for that question (e.g. `{"cant_leave_alone":[{"who":"mom","need":"power wheelchair"}]}`) + a short acknowledgment (≤12 words) | `agent/llm.py: extract()` |
| 2 | **Check the Harvey aerial photos** | A 512 px Harvey after-flood aerial image | `{"verdict":"flooded"/"not_flooded"/"uncertain","explanation":…}`. 17 of 21 Bear Creek images flagged flooded | `agent/content.py: imagery_check()` |
| 3 | **Write responder house cards** | The household's record | ≤35-word card for a rescue crew ("2 people; mom uses a power wheelchair, ~400 lb, bring 2–3 lifters; no water inside; English") | `house_card()` |
| 4 | **Brief the incident commander** | Status counts + top of the rescue queue at minute 10/30/60 | ≤60-word situation summary | `briefing()` |
| 5 | **Play residents for testing** | A hidden persona (true facts + speaking style, ~10% Spanish) + the agent's question | What that resident would say | `agent/simulate.py` |

**What Qwen does NOT do (by design):**
- It **doesn't choose the questions or their order.** The code does (`agent/script.py`).
- It **doesn't decide who gets rescued.** Ranking and routing are transparent rules and shortest-path math (`pipeline/dispatch.py`).
- It **can't promise help or say "you're safe."**
  - Every sentence about help is a fixed template chosen by code.
  - A guard deletes any model line containing a banned phrase. In testing it blocked 48 such lines; **0 were spoken.**
- It **can't invent people.** A person is only recorded if their words appear in what the resident actually said. A bare "yes" to "can anyone not leave?" makes the agent ask "Who is it, and what do they need?" instead of guessing.

**Why this split:** language models are good at understanding messy speech ("it's me and my mom… no wait, she's on oxygen") and bad at being reliable decision-makers. So the model *reads*, and the code *decides*.

**How we make the model's output reliable:**
- **Structured output.** We send a JSON schema with every request, and the server forces the reply into it. All keys are required (`null` = not answered), because the model skips optional keys.
- **A fallback.** If the reply can't be parsed, the turn counts as "nothing understood" and the question is asked once more.
- **Temperature 0**, so the same input gives the same output.

## One live call, step by step
1. The dashboard's Run Demo (scene 6) calls our server: `POST /api/demo-call`.
2. Our server asks Retell's API to dial the demo phone from our Retell number, tagged with the house ID (`h050`).
3. You answer. Retell opens a WebSocket to the **relay**, which passes it through the laptop's open connection to **our server** (`/llm-websocket/{call_id}`).
4. Our server sends the opening line: *"This is Swift, an automated flood assistant working with local emergency services. Am I speaking with someone at 1586 Eagle Trail Drive?"* Retell speaks it.
5. You answer. Retell transcribes it and sends the text to our server.
6. Our server sends that text to **Qwen** (job 1), which returns the facts as JSON plus a short acknowledgment.
7. The **script** updates the record, decides the next step (next question, re-ask, "Who is it…?" follow-up, read-back, or "What should I fix?") and sends the line back. Retell speaks it.
8. Steps 5–7 repeat for: people at home → who can't leave and why → water inside? → truck/boat/seats → read-back.
9. At the end: a fixed closing line for the status, Qwen writes the house card, and the call hangs up.
10. Retell posts a webhook when the call ends. If you didn't answer, busy, or voicemail, the house is marked ⚫ no answer.
11. The whole time, the dashboard polls `GET /api/live` every 2 s. The transcript streams into house h050's drawer, and the house turns red.

If anything in the chain fails, the dashboard plays `live_fallback.json`, which is the same rehearsal call recorded through the real model.

## What data the voice agent collects
Exactly one record per household (`records/{id}.json`, shape in `CONTRACT.md`):

| Field | Example | Why a responder needs it |
|---|---|---|
| `people` | `2` | How many seats and how many people to find |
| `cant_leave_alone` | `[{"who":"mom","need":"power wheelchair"}]` | Who needs help and what equipment or crew: a power chair is ~400 lb (2–3 lifters), oxygen, bedbound → stretcher |
| `water_inside` | `false` | Urgency |
| `can_help` | `{"truck":true,"boat":false,"seats":3}` | Neighbors who can rescue others (26 of the 35 replay trips used neighbors' vehicles) |
| `language` | `"en"` / `"es"` | So the crew can talk to them |
| `status` | `needs_help` / `can_help` / `safe` / `unconfirmed` / `no_answer` | Map color and rescue queue |
| `transcript`, `attempts`, `house_card` | | Audit trail, retries, the crew's card |

**Not collected:** names, dates of birth, insurance, diagnoses beyond what affects leaving, or audio. Retell keeps its own call recording by default; that can be switched off in a real deployment.

**Where it lives:** in memory on our server and in local JSON files. The model sees only the current turn's text. In a real deployment, the model and the records would sit on hardware the agency controls (that's the point of a local GB10), so medical information never goes to a public AI service.

## How the replay data was built (the pipeline)
1. **Pick the area.** We used the UTSA dataset's image locations to find Bear Creek (west Houston, next to the Addicks Reservoir). The reservoir pool backed into it in Harvey, and about two-thirds of its homes flooded.
2. **Homes and roads.** 150 real buildings and the drive network from OpenStreetMap.
3. **Flood depth.** USGS 10 m elevation → "height above the lowest point within 1 km" (a quick terrain screen called HAND-lite) against a water level that rises over 6 hours to 12 ft, shaped by the dataset's Harvey rainfall.
   - Result: 81 of 150 homes flood, with water arriving between minutes 121 and 321, up to 9 ft deep.
4. **Call order.** Earliest water first, 20 lines at once. Non-answers are retried at +2 and +5 min, then sent to the door-knock list.
5. **Calls.** 150 simulated residents through the real script and Qwen. Results:
   - **91.5%** of statuses correct;
   - **all 34** households that truly needed help were flagged;
   - **0** promises spoken.
6. **Dispatch.**
   - Ranking: can't-leave > water inside > deeper > sooner.
   - Routes: shortest path on the road network, skipping streets deeper than the vehicle can handle (high-water truck 3 ft; boats any depth).
   - Door-knock clusters: no-answers within 300 m of each other.
7. **Comparison.** With the same fleet, "wait for 911" reaches **57.1%** of needs-help homes before water arrives, and Swift reaches **100%**.
   - Across **1,000 randomized storms** (peak, no-answer rate, fleet size and 911 reach all varied): median **34.3% vs 82.9%**, with Swift's 10th–90th percentile at 68.6–94.3%.
   - This is a policy simulation, not a lives-saved prediction.

## Dashboard ↔ server API
| Endpoint | Used for |
|---|---|
| `POST /api/demo-call` | Start the live call (Run Demo, scene 6) |
| `GET /api/live` | Live record + call status, polled every 2 s |
| `GET /api/gpu` | "Qwen3-VL on GB10" panel: calls in flight, total calls, average latency |
| `POST /api/simulate-live` | Runs a few simulated calls during the demo so the panel shows real load |
| `/data/*` | The precomputed replay files |

## Likely technical questions from Dell judges
**Why an 8B model and not something bigger?**
- Each call turn is a narrow job (fill a small JSON form from one sentence), and latency matters on a phone call. The 8B model does it in about 0.3–0.4 s.
- Our event key could only use the 8B model; the 32B and 122B models returned 403.
- The vision part of Qwen3-VL also lets the same model read the aerial images.

**What does the GB10 contribute?**
- Every model call runs on it: more than 1,600 so far, including 150 full simulated calls with 8 running in parallel.
- The GB10's 128 GB of unified memory and Blackwell GPU let one box serve many short requests at once. That's the shape of this workload: a county-wide call wave is thousands of tiny extractions, not one big generation.
- On a real deployment, a GB10 in an emergency operations center keeps residents' medical details on hardware the county owns, and still works if the internet is degraded.

**Why not fine-tune the model?** The task is narrow and structured. A JSON schema and code-side rules gave 91.5% accuracy with no training data. Fine-tuning on real call transcripts would be the next step.

**How does it scale to a whole county?** The limit is phone lines, not the model. Each turn is one short request, so a single model server handles many simultaneous calls. Calls are already ordered by when water arrives, so the first lines go to the first-flooded homes.

**What if the model mishears?**
- The script re-asks once if the answer doesn't fit the question.
- It reads the record back and accepts one correction.
- It never drops a "can't leave" once it's recorded.
- Unclear calls end as `unconfirmed` for a human to follow up.

**How accurate is the flood model?** It's a terrain screen, not a hydraulic model: it ignores channels, drains and reservoir operations, and the 12 ft peak is chosen, not forecast. For a real event, it would take river-gauge forecasts from NOAA/NWS instead.

**Spanish?** The extraction handles Spanish (about 10% of the simulated residents spoke it). The live Retell voice is set to English for the demo.

**Privacy?**
- The minimum data needed for a rescue, no names or diagnoses beyond mobility.
- The model sees only the current answer.
- Records stay on the agency's system.
