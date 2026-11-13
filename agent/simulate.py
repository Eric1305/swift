"""Simulated residents for the replay: every household is 'called' through the same script + extraction as the
live phone call, many at once on the GB10. A resident LLM role-plays a persona with hidden ground truth."""
import argparse
import asyncio
import json
import random
import threading
from pathlib import Path

from agent.content import briefing, house_card
from agent.llm import ask, extract
from agent.script import INTRO, CallState, Record, advance, guard, prompt_for, status_of

MIX = [("needs_help", 0.20), ("can_help", 0.15), ("safe", 0.50), ("no_answer", 0.15)]
STYLES = ["plain and short", "rambling", "corrects themselves once", "nervous, short answers"]
NEEDS = [("mother", "power wheelchair"), ("father", "manual wheelchair"), ("husband", "on oxygen"),
         ("grandmother", "bedbound"), ("son", "walker"), ("wife", "recovering from surgery, can't walk")]


def make_personas(households: dict, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    personas = []
    for feature in households["features"]:
        props = feature["properties"]
        roll, status = rng.random(), MIX[-1][0]
        for name, share in MIX:
            if roll < share:
                status = name
                break
            roll -= share
        people = rng.randint(1, 5)
        truth = {"status": status, "people": people, "cant_leave_alone": [], "water_inside": False,
                 "can_help": {"truck": False, "boat": False, "seats": 0}}
        if status == "needs_help":
            if rng.random() < 0.75:
                who, need = rng.choice(NEEDS)
                truth["cant_leave_alone"] = [{"who": who, "need": need}]
            truth["water_inside"] = not truth["cant_leave_alone"] or rng.random() < 0.3
        elif status == "can_help":
            kind = rng.choice(["truck", "boat", "seats"])
            truth["can_help"] = {"truck": kind == "truck", "boat": kind == "boat", "seats": rng.randint(1, 3) if kind == "seats" else 0}
        personas.append({"id": props["id"], "address": props["address"], "truth": truth,
                         "language": "es" if rng.random() < 0.10 else "en", "style": rng.choice(STYLES)})
    return personas


def scripted_reply(persona: dict, step: str) -> str:
    """Fallback resident (no LLM): answers straight from the ground truth."""
    t = persona["truth"]
    if step == "people":
        return f"There are {t['people']} of us here."
    if step == "cant_leave":
        return "; ".join(f"My {p['who']} can't leave alone, {p['need']}." for p in t["cant_leave_alone"]) or "No, everyone can walk out."
    if step == "water_inside":
        return "Yes, water is coming inside." if t["water_inside"] else "No, not inside yet."
    if step == "can_help":
        h = t["can_help"]
        if h["truck"]:
            return "Yes, I have a lifted truck."
        if h["boat"]:
            return "I have a small boat."
        return f"I have {h['seats']} free seats in my car." if h["seats"] else "No, sorry."
    return "Yes, that's right."


def resident_reply(persona: dict, step: str, question: str) -> str:
    language = "Spanish" if persona["language"] == "es" else "English"
    prompt = (
        "You are a resident answering an automated flood-safety phone call. Your true situation: "
        f"{json.dumps(persona['truth'])} (ignore the 'status' key). Your address is {persona['address']}. "
        f"Speaking style: {persona['style']}. Answer in {language}, in one or two short spoken sentences, "
        f"using only your true situation.\nThe caller asked: {question}"
    )
    try:
        return ask(prompt, max_tokens=60) or scripted_reply(persona, step)
    except Exception:
        return scripted_reply(persona, step)


class Gauge:
    """Tracks how many calls run at the same time."""

    def __init__(self):
        self.now = self.peak = 0
        self.lock = threading.Lock()

    def __enter__(self):
        with self.lock:
            self.now += 1
            self.peak = max(self.peak, self.now)

    def __exit__(self, *exc):
        with self.lock:
            self.now -= 1


def run_call(persona: dict, use_llm_resident: bool = True) -> tuple[Record, int]:
    """One simulated call through the real script. Returns the record and how many acks the guard blanked."""
    state = CallState(record=Record(id=persona["id"], address=persona["address"], attempts=1,
                                    language=persona["language"]))
    question = f"{INTRO} {prompt_for(state)}"
    state.record.transcript.append({"who": "agent", "text": question})
    blanked = 0
    while state.step != "close":
        step = state.step
        said = resident_reply(persona, step, question) if use_llm_resident else scripted_reply(persona, step)
        state.record.transcript.append({"who": "resident", "text": said})
        fields, ack = extract(step, said)
        blanked += bool(ack) and not guard(ack)
        state, question = advance(state, fields, ack)
        state.record.transcript.append({"who": "agent", "text": question})
    return state.record, blanked


def simulate_all(households: dict, out: Path, concurrency: int = 8, use_llm_resident: bool = True) -> dict:
    """Call every household (in parallel on the GB10), write records/*.json and briefings.json, return stats."""
    personas = make_personas(households)
    (out / "records").mkdir(parents=True, exist_ok=True)
    gauge = Gauge()

    def one(persona: dict) -> tuple[dict, Record, int]:
        if persona["truth"]["status"] == "no_answer":
            return persona, Record(id=persona["id"], status="no_answer", attempts=3, language=persona["language"]), 0
        with gauge:
            record, blanked = run_call(persona, use_llm_resident)
        if record.status == "needs_help":
            record.house_card = house_card(record)
        return persona, record, blanked

    async def run_all():
        limit = asyncio.Semaphore(concurrency)

        async def guarded(persona):
            async with limit:
                return await asyncio.to_thread(one, persona)

        return await asyncio.gather(*(guarded(p) for p in personas))

    results = asyncio.run(run_all())
    answered = [(p, r) for p, r, _ in results if p["truth"]["status"] != "no_answer"]
    for _, record, _ in results:
        (out / "records" / f"{record.id}.json").write_text(record.model_dump_json(indent=2, exclude={"address"}) + "\n")
    records = [r for _, r, _ in results]
    briefings = [{"t_min": t, "text": briefing(t, records)} for t in (60, 180, 300)]
    (out / "briefings.json").write_text(json.dumps(briefings, indent=2) + "\n")
    correct = sum(status_of(r) == p["truth"]["status"] for p, r in answered)
    spoken = sum(1 for _, r, _ in results for line in r.transcript
                 if line["who"] == "agent" and not guard(line["text"]))
    return {
        "record_accuracy": round(correct / len(answered), 3) if answered else 0.0,
        "promise_violations": spoken,
        "promises_blocked": sum(b for _, _, b in results),
        "parallel_calls": gauge.peak,
        "n_households": len(personas),
        "answers": {p["id"]: p["truth"]["status"] != "no_answer" for p in personas},
    }


REHEARSAL = {"confirm_address": "Yes, that's right.", "people": "Two, me and my mom.",
             "cant_leave": "My mom uses a power wheelchair.", "water_inside": "It's at the front step, not inside yet.",
             "can_help": "No.", "readback": "Yes."}


def write_live_fallback(households: dict, out: Path, demo_id: str, delay_ms: int = 1800) -> dict:
    """Record the rehearsal call through the real script + model, for the demo's no-network fallback."""
    address = next(f["properties"]["address"] for f in households["features"] if f["properties"]["id"] == demo_id)
    state = CallState(record=Record(id=demo_id, address=address, attempts=1))
    lines = [{"who": "agent", "text": f"{INTRO} {prompt_for(state)}"}]
    while state.step != "close":
        said = REHEARSAL[state.step]
        fields, ack = extract(state.step, said)
        state, reply = advance(state, fields, ack)
        lines += [{"who": "resident", "text": said}, {"who": "agent", "text": reply}]
    record = state.record
    record.transcript = lines
    record.house_card = house_card(record)
    fallback = {"record": record.model_dump(exclude={"address"}),
                "steps": [{"delay_ms": delay_ms * i, **line} for i, line in enumerate(lines)]}
    (out / "live_fallback.json").write_text(json.dumps(fallback, indent=2) + "\n")
    return fallback


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate calls to every household through the real script.")
    parser.add_argument("--out", type=Path, default=Path("web/public/data"))
    parser.add_argument("--concurrency", type=int, default=8, help="the hosted model is shared by every team")
    parser.add_argument("--scripted", action="store_true", help="scripted residents instead of LLM role-play")
    args = parser.parse_args()
    households = json.loads((args.out / "households.geojson").read_text())
    stats = simulate_all(households, args.out, args.concurrency, use_llm_resident=not args.scripted)
    results_path = args.out / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    results.update({k: v for k, v in stats.items() if k != "answers"})
    results_path.write_text(json.dumps(results, indent=2) + "\n")
    (args.out / "answers.json").write_text(json.dumps(stats["answers"], indent=2) + "\n")
    print({k: v for k, v in stats.items() if k != "answers"})
    demo_id = json.loads((args.out / "meta.json").read_text())["demo_household_id"]
    fallback = write_live_fallback(households, args.out, demo_id)
    print("live fallback:", fallback["record"]["status"], "|", fallback["record"]["house_card"])
