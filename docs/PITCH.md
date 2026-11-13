# Swift: 3-minute pitch

Timed to the Run Demo scene list in `web/src/demo/director.ts` (PLAN T4). Press **Run Demo** at 0:20, so demo time = pitch time − 20 s. Rubric tags: **[Creativity]**, **[Impact]**, **[LLM/AI]** (creative use of LLMs/AI), **[Data]**, **[Interface]**.

Before going on stage:
- Agent server running (`.venv/bin/uvicorn agent.server:app --port 8080`), relay client running (`.venv/bin/python -m relay.client`), and `https://swift-w7bb.onrender.com/health` shows `"agent_connected": true`.
- Dashboard open at `http://localhost:8080/?flood=pipeline`. Start the call with **Run Demo**, not `curl` (that would make two calls).
- Phone on loud with the ringer on. If the live call fails, the dashboard plays `live_fallback.json` on its own.
- Backup video ready. No pushes to `main` during the demo (a push can redeploy the relay).

## What runs where (for questions)
| Piece | Where | Details |
|---|---|---|
| AI model | Organizers' Dell Pro Max GB10 model server | `http://10.246.100.230/v1`, organizer key, model `qwen3-vl-8b-instruct` (the only model our key can use). Runs every live-call turn, the 150 simulated calls, the aerial-image verdicts, house cards and briefings: 1,600+ calls so far, ~0.3–0.4 s each |
| Phone calls | Retell (phone line, speech-to-text, voice) → Render relay → our FastAPI server on the laptop | Retell never decides what to say; our code and the GB10 model do |
| Flood images + metadata | Hugging Face `jennifer-fowler/UTSA-flood-images` (organizers' dataset) | 1,204 georeferenced Texas images, `image_metadata.csv` with 273 columns. Downloaded once; results are precomputed into `web/public/data/`, so the demo doesn't download anything |
| Homes and roads | OpenStreetMap | 150 real Bear Creek buildings and the drive network, cached in `pipeline/cache/` |
| Ground elevation | USGS 3DEP 10 m DEM | Basis of the flood-depth model, cached in `pipeline/cache/` |

---

### 0:00–0:20 · Hook (slide or the map's title view) [Impact]

> In the 17 hours after Harvey made landfall, Houston's 911 system got more than 56,000 calls. A normal day brings about 8,000. Texas keeps a registry of people who need help evacuating, and Houston's emergency manager said afterward they didn't use it the way they could have, because they were buried in calls. Flood maps didn't help either: Harvey rescue requests had no correlation with FEMA flood zones.
>
> So we flipped it. Instead of waiting for people to get through to 911, Swift calls them.

**Press Run Demo.**

### 0:20–0:25 · Scene 1, fly in (demo 0 s) [Data]

> This is Bear Creek in west Houston, right against the Addicks Reservoir. In Harvey the reservoir backed into it and about 65% of the subdivision's homes flooded. These are 150 real buildings from OpenStreetMap on USGS 10-meter elevation.

### 0:25–0:45 · Scene 2, water rises and calls fan out (demo 5 s) [Creativity] [LLM/AI]

> The water you see is the real Addicks Reservoir level the USGS gauge recorded during Harvey: three and a half days, compressed into six hours. The reservoir surface is nearly flat, so with USGS elevation data for every house, the lowest homes flood first. Swift doesn't predict exactly which homes will flood; it uses that order, from only what the gauge had published when the calls started: lowest ground, first call. A home that doesn't pick up is retried at two and five minutes and then goes on a door-knock list, because silence never counts as safe.
>
> Top right: those are real requests going to Qwen3-VL on the event's model server right now. Every reply on every call is decided by that model and our code. Retell only carries the voice.

### 0:45–0:55 · Scene 3, top-ranked house opens (demo 25 s) [Interface] [LLM/AI]

> Red means someone can't leave on their own. Here's the transcript, the structured record, and a responder card the model wrote: who is home, the power chair, roughly how heavy it is, how many people to bring. The queue on the left ranks homes by who can't leave, water inside, depth and time left.

### 0:55–1:15 · Scene 4, vehicles move (demo 35 s) [Creativity] [Impact]

> 63% of flood deaths with a known cause are in vehicles, so routing matters. High-water trucks only take streets under three feet, and boats go anywhere. Orange homes told us they have a truck, a boat or free seats, and they become part of the fleet. The dashed outlines are door-knock clusters. The commander briefing on the left is written by the model.

### 1:15–1:25 · Scene 5, Harvey aerials (demo 55 s) [Data] [LLM/AI]

> These are real NOAA aerials taken after Harvey, placed at their true footprints, with before images from 2016. The dataset had no flood labels, so Qwen3-VL looked at each one: 17 of 21 show flooding, with a one-line reason for each.

### 1:25–2:25 · Scene 6, live call (demo 65 s) [LLM/AI] [Interface]

> Now a real call. This house is mine.

*Phone rings. Answer on speaker. The agent opens: "This is Swift, an automated flood assistant working with local emergency services. Am I speaking with someone at …?"*

| Agent asks | Eric says |
|---|---|
| Address | "Yes, that's right." |
| How many people | "Two, me and my mom." |
| Anyone who can't leave alone | "My mom uses a power wheelchair." |
| Water inside | "It's at the front step, not inside yet." |
| Can you help neighbors | "No." |
| Read-back | "Yes." |

*The house turns red, and the record and house card appear in the drawer.*

> Notice what it didn't say. It never says help is on the way, and it never says I'm safe. It said, "No responder has been assigned yet." That rule is in code: the model only extracts facts, and anything it writes passes a filter that blocks promises in English and Spanish. In testing, the filter caught 47 such lines, and none of them were spoken.

*If no ring after ~15 s, or the call drops:* "The venue network is fighting us, so this is the recording of the same call." The fallback plays automatically after 90 s, or switch to the second tab.

### 2:25–2:50 · Scene 7, results card [Impact] [Data]

> We replayed Harvey on 150 real homes in Bear Creek, mapped from OpenStreetMap, using the actual reservoir gauge readings and USGS elevation data for every house. The lowest ground floods first, so that's Swift's calling order. Using only what was known that night, that order reached every home that flooded at least a day before the water got there, and got everyone who needed help out before their street went under. When people had to get through to 911 themselves, fewer than half made it: 42.9%, with the same vehicles.
>
> We tested the calls with 150 simulated residents, each role-played by the model with a hidden truth. Swift recorded the right status for 91.5% of them and flagged all 34 who truly needed help. Over 1,000 randomized storms the median goes from 28.6% to 82.9%. The residents are simulated, so this is a policy comparison, not a prediction; the water and the timing are real.

### 2:50–3:00 · Close [Impact]

> In a real event, the trigger is an NWS warning, the water comes from the live gauge feed and forecasts, the phone list comes from reverse-911 and the STEAR registry, and the same loop runs. Swift: call everyone, in the order the water arrives.

---

## Q&A appendix

**1. What if the model gets it wrong?**
It decides very little. Code chooses every question and every closing message. The model fills a strict JSON schema, and a person is only recorded if they're in the resident's own words. A bare "yes" gets a follow-up ("Who is it, and what do they need?"), an answer that doesn't fit the question is asked once more, and if the output doesn't parse, the turn counts as "nothing extracted". The read-back step reads the whole record to the resident and accepts corrections. Someone recorded as unable to leave is never dropped by a later turn. Any call we can't confirm ends as `unconfirmed`, and those homes are followed up by a person. On 150 simulated residents, 91.5% ended with the right status, and all 34 who truly needed help were flagged; the misses are cautious ones (safe homes left unconfirmed).

**2. Isn't it dangerous for an AI to talk to people in an emergency?**
That's why it can't promise anything. Help-related sentences are fixed templates, and model text containing phrases like "help is on the way", "you're safe" or "estamos enviando" is blanked before it's spoken. The agent tells people to call 911 if water is rising inside, and not to drive through flooded roads. It adds information to dispatch and doesn't replace 911.

**3. What about privacy of medical information?**
We ask only what a responder needs: who can't leave and why, for example "power wheelchair" or "oxygen". Records stay on the agency's server, and the model runs on hardware the agency controls (here, the GB10 server). Nothing goes to a third-party LLM API. Retell carries the audio. A production version would use a telephony provider under the agency's contract, plus retention limits and access logging.

**4. Why phone calls and not an app?**
Calls work on any phone, including landlines, with no install and no data plan. The people most likely to need help, older residents and people with disabilities, are also the least likely to have installed a new app before a storm. A call is also two-way: an alert can't tell you who is still inside.

**5. How does it scale to a whole county?**
Each turn is one short extraction, about 0.2–0.4 s on an 8B model, so one model server handles many calls at once. The limit is phone lines, and the scheduler already runs N lines in parallel. Ordering by water arrival means the first calls go to the homes with the least time, so even a partial run helps the right people first. Telephony trunks (Retell or Twilio) scale to hundreds of concurrent lines.

**6. Where does the model run, and what does it do?**
It's the organizers' Dell Pro Max GB10 model server, serving Qwen3-VL-8B (`qwen3-vl-8b-instruct`) with the event's shared key. It runs every model call: each live call turn, the simulated residents (both the resident and the agent side), the aerial-image verdicts, the house cards and the commander briefings. The dashboard panel shows our in-flight requests, total calls and latency against that server live. The depth model, routing and Monte Carlo are NumPy on the laptop. They run on GPU through a CuPy shim when one is present, but the organizers took back the per-team workstations mid-event.

**7. How accurate is your depth model? Would it have worked during Harvey?**
The water level isn't made up. It's the Addicks Reservoir pool recorded by USGS gauge 08073000 during Harvey, in the same datum as the 3DEP elevation. Bear Creek flooded because that pool backed up, so depth is pool minus ground wherever the ground connects to the water. Swift itself only sees what existed when calls started at midnight Aug 27: the elevation data and the gauge readings published so far, which showed the pool rising about 12 feet a day. That gives every home an ETA. The ETAs run early, which is the safe direction, and match the order the water actually arrived with a rank correlation of 0.996, and a test proves later readings can't change them. Limits: daily rather than hourly readings, bare-earth elevation rather than floor heights, no rain ponding, and no house-by-house check against high-water marks yet. Qwen3-VL saw flooding in 17 of the 21 real aerials in the same area, which is consistent.

**8. What about people who don't speak English?**
The extraction prompt, the schema (it records `language`) and the honesty filter handle English and Spanish. About 10% of our simulated residents answered in Spanish. Our live voice agent is English today. Next is choosing the voice and the script templates by registered or detected language, and using the reverse-911 list's language field where it exists.

**9. Where does the 100% vs 42.9% come from? Isn't that too good?**
That's one replay night with 35 needs-help homes and the same 3 vehicles for both sides. In the baseline, 55% of needs-help homes reach 911, 20 minutes before their water, and are served first come, first served. Swift knows about each home when its call finishes and serves them by rank. The fairer number is the Monte Carlo: over 1,000 nights with random pool rise speed, no-answer rate, fleet size and 911 reach rate, the median is 28.6% vs 82.9%, and Swift's 10th–90th percentile is 68.6–94.3%. These are synthetic residents, so it's a policy comparison, not a lives-saved estimate.

**10. People don't answer unknown numbers. Won't they ignore it?**
Some will, and that's built in. No answer after two retries puts the home on the door-knock list, clustered within 300 m so a crew can walk it. In the replay, 21 homes ended up in 11 clusters. In a real deployment, calls should come from the county's known alert number.

**11. How is this different from CodeRED or Wireless Emergency Alerts?**
Those systems broadcast one way. Swift has a conversation and returns a structured record: who is there, who can't leave, whether water is inside, who has a boat. In the Kerr County flood the NWS warning went out at 1:14 a.m. and the county's CodeRED alert went out hours later. Swift could start dialing as soon as a warning is issued, and it tells dispatch who answered.

**12. What data did you add beyond the provided dataset?**
The provided dataset is the organizers' Hugging Face set `jennifer-fowler/UTSA-flood-images` (1,204 georeferenced images, 273 metadata columns). On top of it we added USGS 3DEP elevation, OpenStreetMap buildings and roads, and the published Harvey research behind the problem statement. From the UTSA dataset we used the image footprints to choose the area, the 2017/2016 after/before aerials, and the 3-day precipitation column as context. The water level itself comes from USGS gauge 08073000 at the Addicks Reservoir.

**Where is the call data stored?**
In a local SQLite database on our server (`data/swift.db`). There's one row per household with its latest state (people, who can't leave and why, water inside, truck/boat/seats, language, the responder card), and one row per call with the full transcript and how the call ended. It's saved after every answer, so nothing is lost if the server restarts. The model never sees the database, only the current answer. In a real deployment it would live on the county's own machine.

