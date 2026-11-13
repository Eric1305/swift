# Swift

When a flood threatens a neighborhood, Swift's AI agent phones every household in the order the water is predicted to reach them. On each call it records who needs help getting out, who can help (a high-clearance truck, a boat, free seats) and who is able to leave on their own. Households that never pick up go on a door-knock list, because silence never counts as safe. Dispatchers see all of this on one map, with a ranked rescue queue and vehicle routes that avoid streets too deep for each vehicle. Retell handles the phone line and the voice. Every reply on the call is decided by our server, which uses Qwen3-VL-8B running on the organizers' Dell Pro Max GB10 model server. The agent is never allowed to promise rescue or to tell anyone they are safe, and that rule is enforced in code, not left to the prompt.

Built for the UTSA × Dell Social Impact AI Datathon. The demo replays Hurricane Harvey in Bear Creek, west Houston, and then places one live call to the presenter's phone.

## The problem

- **911 is overwhelmed when it is needed most.** In the 17 hours after Harvey made landfall, Houston's 911 system received more than 56,000 calls. A typical 24-hour period brings about 8,000 ([AP via Fox News, Aug 28 2017](https://www.foxnews.com/us/the-latest-houston-officials-hunker-down-stay-off-roads)). The figure was also reported from Mayor Sylvester Turner's briefing as 56,000 calls since 10 p.m. Saturday ([Los Angeles Times via Governing](https://www.governing.com/archive/tns-houston-hurricane-harvey.html)). People who need help most often can't get through.
- **The disability registry went unused.** Texas keeps the STEAR registry so that responders know who needs help evacuating. Houston's emergency manager said afterward, "We did not use the STEAR structure as it could've been used," because the office was "tied up with ... the high call volumes." It remains unclear how many registrants got help through it ([Texas Tribune, Aug 22 2018](https://www.texastribune.org/2018/08/22/did-state-registry-help-people-disabilities-during-harvey); [Governing reprint](https://www.governing.com/archive/tt-hurricane-harvey-texas-emergency-registry.html)).
- **Flood maps don't predict who needs rescue.** A study of 7,453 Red Cross rescue requests in the Houston area during Harvey (Aug 27–30) found that the request rate was "statistically uncorrelated with the percentage of flood hazard zone designated by" FEMA ([Feng, Shao & Lin, *Findings*, 2022](https://doi.org/10.32866/001c.37903)). Swift asks people directly instead of guessing from a zone map.
- **Driving into water is the leading cause of flood deaths.** Across 2,461 US flood fatality records from 1996 to 2023, 63% of deaths with a known cause were vehicle-related ([CIRA, Colorado State University, 2025](https://www.cira.colostate.edu/science-stories/what-is-responsible-for-most-inland-flood-fatalities/)). In Texas, vehicle-related deaths were 58% of all flood fatalities from 1959 to 2019 ([Sharif & Han, *Water*, "Vehicle-Related Flood Fatalities in Texas, 1959–2019"](https://rrpress.utsa.edu/items/8a0eb964-1a3e-4bf8-b2c4-084fdd65b29c/full)). This is why Swift routes rescue vehicles only along streets shallow enough for them, and why the call tells people not to drive through flooded roads.
- **Warnings don't reach people in time.** In the July 2025 Hill Country flood, the NWS issued a Flash Flood Warning for Kerr County at 1:14 a.m. The sheriff told lawmakers the county's CodeRED alert went out at 5:01 a.m., and KSAT found no record of a CodeRED alert before 5:34 a.m. ([KSAT timeline, Aug 3 2025](https://www.ksat.com/news/local/2025/08/03/flood-timeline-alerts-emergency-response-and-pivotal-moments-in-july-4-tragedy-in-the-hill-country)). A one-way alert also returns no information about who is still inside.
- **Why Bear Creek.** Bear Creek Village sits against the Addicks Reservoir in west Houston. During Harvey the reservoir pool backed up into the neighborhood. The homeowners association reported that about 65% of its 1,900-plus homes flooded, some with more than six feet of water ([KHOU](https://www.khou.com/article/news/local/neighborhood/in-bear-creek-village-residents-demanding-action-to-prevent-future-flooding/285-584478037); [KPRC](https://www.click2houston.com/news/2018/08/27/life-near-the-reservoirs)). Downstream, the Army Corps' controlled releases from Addicks and Barker flooded homes along Buffalo Bayou ([Houstonia](https://www.houstoniamag.com/articles/barker-addicks-reservoirs-release-west-houston-memorial-energy-corridor-hurricane-harvey)).

## How it works

```text
 households (OSM footprints + addresses)
      │  predicted water arrival per home (3DEP DEM, HAND-lite depth model)
      ▼
 call scheduler ── dials in water-arrival order, N lines in parallel,
      │            retries no-answers at +2 and +5 min
      ▼
 Retell (phone line, speech-to-text, voice)
      │  ▲   WebSocket, one per call
      ▼  │
 our server (agent/server.py) ── code picks the next question, applies the honesty guard
      │  ▲
      ▼  │
 Qwen3-VL-8B on the Dell Pro Max GB10 model server ── extracts facts + a short acknowledgment
      │
      ▼
 household records: needs_help / can_help / safe / unconfirmed / no_answer
      │
      ├─► rescue queue (ranked: can't leave alone, water inside, depth, arrival time)
      ├─► depth-aware routes (high-water vehicles ≤ 3 ft, boats any depth, neighbor trucks and boats)
      └─► door-knock list (no-answer homes clustered within 300 m)
      │
      ▼
 dashboard (React + deck.gl): rising water, call arcs, colored homes, vehicle trips,
 Harvey aerials with model verdicts, commander briefings, live "calls in flight" panel
```

The call follows a fixed script written in code (`agent/script.py`): confirm the address, ask how many people are home, ask whether anyone can't leave on their own (wheelchair, oxygen, bedbound, and whether a wheelchair is powered), ask whether water is inside, ask whether they can help neighbors, read the record back, and close. The model never chooses what to ask. On each turn it does one job: it turns what the resident said into structured fields under a strict JSON schema and writes an acknowledgment of 12 words or fewer. A correction ("no wait, it's three of us") overwrites the earlier answer, but a person recorded as unable to leave is never dropped. A silent or unclear turn is re-asked once, then the call moves on. Each turn takes about 0.2–0.4 s on the hosted model.

## Where AI runs

Every model call goes to `qwen3-vl-8b-instruct` on the organizers' Dell Pro Max GB10 model server (OpenAI-compatible, `agent/llm.py`).

| Use | What the model does | Code |
|---|---|---|
| Live phone calls | Per-turn fact extraction (people, who can't leave and why, water inside, truck/boat/seats, language) plus a short acknowledgment. Retell only carries the audio. | `agent/llm.py: extract`, `agent/server.py` |
| Harvey aerial imagery | Looks at each post-Harvey NOAA aerial in the area and returns `flooded` / `not_flooded` / `uncertain` with a short reason. The dataset's own `flood_visible` column is empty, so these are the only labels. 17 of 21 images were judged flooded. | `agent/content.py: imagery_check` |
| Responder house cards | A card of 40 words or fewer for each needs-help home, e.g. "Two people live here. Mom needs power wheelchair and can't leave alone. No water inside. Language: English. Power chair: ~400 lb, bring 2-3 lifters." | `agent/content.py: house_card` |
| Commander briefings | A summary of 60 words or fewer at t = 60, 180 and 300 min: counts by status, mobility needs, and available neighbor vehicles. | `agent/content.py: briefing` |
| Simulated residents (evaluation) | A second model role plays 150 residents with hidden ground truth and different speaking styles (plain, rambling, self-correcting, nervous; about 10% Spanish). Each is "called" through the same script and extraction as the live call, 8 at a time. | `agent/simulate.py` |

The dashboard's model panel polls `/api/gpu` and shows "Qwen3-VL on GB10 · calls in flight · calls · latency". During Run Demo, a background simulation sends real requests so the in-flight count moves.

## Data

| Source | Used for |
|---|---|
| [UTSA flood images dataset](https://huggingface.co/datasets/jennifer-fowler/UTSA-flood-images) (1,204 georeferenced Texas images, 273 metadata columns) | Picking the study area (densest cluster of Harvey response images), 21 NOAA 2017 after-images and their 2016 NAIP before-images draped at their true footprints, and the storm's 3-day rainfall (`preceding_3d_precipitation_mm`, 660 mm median in the area). This rainfall shapes the water-rise curve. |
| USGS 3DEP 10 m DEM (via `py3dep`) | Ground elevation for the depth model |
| OpenStreetMap buildings and drive network (via `osmnx`) | 150 sampled household footprints, addresses and the routing graph |

**Depth model (HAND-lite, `pipeline/depth.py`).** Each cell's height above the lowest point within 1 km is compared with a water level that rises along a rainfall-shaped logistic curve to 12 ft over 6 hours. Depth = max(0, rise − height). A home's water arrival is the first minute its depth exceeds 0.5 ft. In the replay, 81 of 150 homes flood, with arrivals between 121 and 321 minutes and peak depths up to about 9 ft.

## Results

From `web/public/data/results.json`, using seed 7 and 150 households.

| Metric | Value | What it means |
|---|---|---|
| Record accuracy | **91.5%** | Share of simulated residents whose final status (needs help / can help / safe / unconfirmed / no answer) matches their hidden ground truth |
| Needs-help homes flagged | **34 of 34** (1 false alarm) | Every simulated household that truly needed help was recorded as needs help. The misses are cautious ones: 5 safe homes left "unconfirmed" and 5 helpers recorded as safe |
| Promises spoken to residents | **0** | Lines that reached a resident and implied rescue or safety |
| Promises blocked by the guard | **48** | Model acknowledgments that contained a banned phrase and were blanked before they were spoken |
| Needs-help homes reached before water arrives (replay night) | **911 baseline 57.1% → Swift 100%** | Same fleet of 3 vehicles. In the baseline, 55% of needs-help homes get through to 911, 20 min before their water arrives, and are served first come, first served. Swift knows every needs-help home once its call completes and serves them in rank order. |
| 1,000 randomized nights (Monte Carlo) | **median 34.3% → 82.9%** (Swift p10–p90: 68.6–94.3%) | Each night varies peak rise (8–16 ft), no-answer rate (5–30%), fleet (2–5 vehicles) and 911 reach rate (30–70%) |
| Parallel call lines in the simulation | 8 | Kept low because every team shares the hosted model |

Replay outcome: 77 safe, 35 need help, 12 can help, 5 unconfirmed, 21 no answer (11 door-knock clusters), and 35 vehicle trips: 9 by the agency fleet (2 high-water vehicles, 1 boat) and 26 by neighbors' trucks and boats offered on the calls.

**Caveats.**
- The households are real OSM buildings, but the residents are synthetic. The personas and their mix (20% need help, 15% can help, 50% safe, 15% no answer) are ours, and the accuracy figure measures how well our system reads LLM-simulated residents, not real people under stress.
- HAND-lite is a terrain screen, not a hydraulic model. It ignores channel flow, storm drains and the reservoir's actual operations, and the 12 ft peak is chosen, not forecast.
- The baseline and Monte Carlo are policy simulations that compare two ways of learning who needs help under the same assumptions. They are not a prediction of lives saved. The 100% on the replay night comes from a small number of needs-help homes (35) and a generous fleet. The Monte Carlo range is the more honest number.

## The honesty rule

The agent never says help is coming and never tells anyone they are safe.

- Every sentence about help is a fixed template in `agent/script.py`. For example, `needs_help` closes with: "I've recorded that you need help leaving. No responder has been assigned yet. If water is rising inside, move to the highest floor and call 911 if you can get through."
- Any model-written text (acknowledgments, house cards, briefings) passes through `guard()`. It blanks the whole line if the text contains a banned phrase in English or Spanish, such as "help is on the way", "we're sending", "someone is coming", "you're safe", "estamos enviando" or "está a salvo".
- The model also only extracts facts. Code decides the next question and the closing message.
- Tests cover this: `tests/test_script.py::test_guard_blanks_promises`.

## How it would work in a real event

The pipeline takes `--source replay` today. A live deployment swaps the inputs and keeps the same outputs, dashboard and call loop.

| Replay today | Real event |
|---|---|
| Harvey replay clock | Triggered by NWS Flood / Flash Flood Warnings for the area (`api.weather.gov/alerts`) |
| Rainfall-shaped rise curve to 12 ft | Stage forecasts from NWS river forecast points and USGS gauges, mapped onto the same HAND-lite grid (`rise_curve(source)`) |
| 150 sampled OSM buildings, synthetic residents | Address and phone lists from county reverse-911 / CodeRED systems, with STEAR registrants flagged and called first within their arrival window |
| Modeled depth on streets | Modeled depth corrected by live reports: road-closure feeds, gauge readings, and residents saying "water is at the front step" |
| One Retell number, one live call | Retell or Twilio trunks with many concurrent lines; the scheduler already runs N lines in parallel |
| Simulated callers on a shared model | A dedicated model server sized for the call volume; each turn is one short extraction |

## Limitations and next steps

- **Language.** The extraction schema and guard handle English and Spanish, and the simulation includes Spanish-speaking residents. The live Retell voice is English only for now. Next: pick the voice and script by the detected or registered language.
- **Validation with real people.** Every accuracy number here comes from LLM-simulated residents. Next: scripted test calls with volunteers, and review by emergency managers and disability advocates.
- **Depth model.** HAND-lite should be replaced or calibrated with a hydraulic model or the NWS National Water Model, and checked against Harvey high-water marks.
- **Privacy.** Records hold medical and mobility details. They stay on the agency's server and go only to the model server for extraction, and nothing is sent to a third-party LLM. A real deployment needs a retention policy and access controls.
- **Trust.** An unknown number calling during a disaster may be ignored or mistaken for a scam. Calls should come from a number residents already know (the county's alert number), and the door-knock list exists because some people will never answer.
- **Infrastructure.** The model server is only reachable on the venue network, so the live call needs a tunnel or relay from the laptop to Retell.

## Repo layout
| Path | What |
|---|---|
| `CONTRACT.md` | The data contract between the backend and the dashboard. **Read this first.** |
| `web/` | Dashboard (React + deck.gl). Reads `web/public/data/` |
| `web/public/data/` | Fixture files generated by the pipeline (real Harvey replay outputs) |
| `pipeline/` | Flood depth, call schedule, routing, Monte Carlo (Python) |
| `agent/` | Call script, Retell custom-LLM server, simulated residents, imagery/house cards/briefings |
| `tests/` | Small pytest suite (8 tests, no model server needed) |
| `docs/PLAN.md` | Build plan and design decisions |
| `docs/PITCH.md` | 3-minute pitch script and judge Q&A |

## Frontend quick start
```bash
cd web
npm install
npm run dev          # http://localhost:5173, reads web/public/data/
```
Leave `VITE_API_URL` empty to run fully offline. The live-call scene then plays `live_fallback.json`, and the model panel shows `gpu_sample.json`. Set `VITE_API_URL` to the agent server's URL to use live endpoints. `npm run build` writes `web/dist`, which the agent server serves at `/`.

## Backend quick start
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[geo]" pytest
cp .env.example .env            # model server defaults are filled in; add Retell keys + phone numbers
.venv/bin/pytest -q
.venv/bin/uvicorn agent.server:app --port 8080
```
Retell has to reach the server's WebSocket (`/llm-websocket/{call_id}`) and webhook (`/retell/webhook`) at a public URL. Put that URL in Retell and in `PUBLIC_URL`, for example with `cloudflared tunnel --url http://localhost:8080` where the network allows it. Then `curl -X POST localhost:8080/api/demo-call` rings `DEMO_PHONE`.

Regenerate the fixtures (needs the model server and the dataset at `~/Texas_Flood_Student_Data`):
```bash
.venv/bin/python -m pipeline.build --source replay --stage base --out web/public/data
.venv/bin/python -m agent.content --out web/public/data
.venv/bin/python -m agent.simulate --out web/public/data
.venv/bin/python -m pipeline.build --source replay --stage dispatch --out web/public/data
```

**The model server (`http://10.246.100.230/v1`, model `qwen3-vl-8b-instruct`) is only reachable on the venue network that routes to `10.246.x.x`.** Away from it, the dashboard still runs entirely from the precomputed fixtures.

## Team
- **Eric Lee**: backend and AI (call script, model integration, Retell server, depth model, routing, simulation)
- **Josie**: frontend (dashboard, map layers, Run Demo director)

## Sources
- AP, "The Latest: Houston officials: hunker down, stay off roads," via Fox News, Aug 28 2017. https://www.foxnews.com/us/the-latest-houston-officials-hunker-down-stay-off-roads
- Pearce & Jarvie, *Los Angeles Times*, via Governing, Aug 28 2017. https://www.governing.com/archive/tns-houston-hurricane-harvey.html
- Evans, "Did a state registry help people with disabilities during Harvey?", *Texas Tribune*, Aug 22 2018. https://www.texastribune.org/2018/08/22/did-state-registry-help-people-disabilities-during-harvey (reprint: https://www.governing.com/archive/tt-hurricane-harvey-texas-emergency-registry.html)
- Feng, Shao & Lin, "Social-Geographical Patterns of Rescue Requests During Hurricane Harvey," *Findings*, 2022. https://doi.org/10.32866/001c.37903
- CIRA, Colorado State University, "What is responsible for most inland flood fatalities?", 2025. https://www.cira.colostate.edu/science-stories/what-is-responsible-for-most-inland-flood-fatalities/
- Sharif & Han, "Vehicle-Related Flood Fatalities in Texas, 1959–2019," *Water*. https://rrpress.utsa.edu/items/8a0eb964-1a3e-4bf8-b2c4-084fdd65b29c/full
- KSAT, "Flood timeline: alerts, emergency response and pivotal moments in July 4 tragedy in the Hill Country," Aug 3 2025. https://www.ksat.com/news/local/2025/08/03/flood-timeline-alerts-emergency-response-and-pivotal-moments-in-july-4-tragedy-in-the-hill-country
- KHOU, "In Bear Creek Village, residents demanding action to prevent future flooding." https://www.khou.com/article/news/local/neighborhood/in-bear-creek-village-residents-demanding-action-to-prevent-future-flooding/285-584478037
- KPRC Click2Houston, "Life near the reservoirs," Aug 27 2018. https://www.click2houston.com/news/2018/08/27/life-near-the-reservoirs
- Houstonia, "Troubled Waters." https://www.houstoniamag.com/articles/barker-addicks-reservoirs-release-west-houston-memorial-energy-corridor-hurricane-harvey
- UTSA flood images dataset. https://huggingface.co/datasets/jennifer-fowler/UTSA-flood-images
- Retell custom LLM docs. https://docs.retellai.com/integrate-llm/overview
