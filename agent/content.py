"""LLM content on the GB10: Harvey imagery check, responder house cards, commander briefings."""
import argparse
import csv
import json
import os
import random
import re
from pathlib import Path

from agent.llm import ask
from agent.script import Record, guard

DATA_DIR = Path(os.environ.get("SWIFT_DATA_DIR", Path.home() / "Texas_Flood_Student_Data"))

# image_metadata.csv has no coordinates, only a locality name; pins are approximate and labeled so.
LOCALITY_CENTROIDS = {
    "bear creek": (-95.648, 29.822),
    "eldridge": (-95.622, 29.772),
    "kingwood": (-95.199, 30.050),
}
DEFAULT_CENTROID = (-95.645, 29.820)

IMAGERY_PROMPT = (
    "Is floodwater visibly covering roads or land around houses? An ordinary river or pond alone is not "
    'flooding. Reply JSON {"verdict":"flooded|not_flooded|uncertain","explanation":"<=20 words"}'
)


def _first_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _centroid(locality: str) -> tuple[float, float]:
    key = next((name for name in LOCALITY_CENTROIDS if name in locality.lower()), None)
    return LOCALITY_CENTROIDS[key] if key else DEFAULT_CENTROID


def imagery_check(image_ids: list[str] | None, out: Path, data_dir: Path = DATA_DIR) -> list[dict]:
    """Ask Qwen3-VL whether each Harvey after-image shows flooding. Writes imagery.json + 512 px thumbs."""
    from PIL import Image

    with open(data_dir / "image_metadata.csv", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r.get("state", "Texas") == "Texas"]
    if image_ids is None:
        image_ids = [r["image_id"] for r in rows if r["image_id"].endswith("_2017_NOAA")]
    by_id = {r["image_id"]: r for r in rows}
    rng = random.Random(7)
    (out / "img").mkdir(parents=True, exist_ok=True)
    results = []
    for image_id in image_ids:
        row = by_id[image_id]
        path = data_dir / row["image_path"]
        thumb = out / "img" / f"{image_id}.jpg"
        with Image.open(path) as image:
            image.convert("RGB").resize((512, 512)).save(thumb, quality=85)
        try:
            data = _first_json(ask(IMAGERY_PROMPT, image_path=str(thumb), max_tokens=80))
        except Exception:
            data = {}
        verdict = data.get("verdict") if data.get("verdict") in ("flooded", "not_flooded", "uncertain") else "uncertain"
        lon, lat = _centroid(row.get("locality", ""))
        results.append({
            "image_id": image_id,
            "lon": round(lon + rng.uniform(-0.004, 0.004), 5),
            "lat": round(lat + rng.uniform(-0.003, 0.003), 5),
            "thumb": f"img/{image_id}.jpg",
            "verdict": verdict,
            "explanation": f"{data.get('explanation', 'No explanation returned.')} (approx. location: {row.get('locality', '')})",
        })
    (out / "imagery.json").write_text(json.dumps(results, indent=2) + "\n")
    return results


def _card_fallback(rec: Record) -> str:
    needs = "; ".join(f"{p.get('who')}: {p.get('need')}" for p in rec.cant_leave_alone) or "none reported"
    water = "water inside" if rec.water_inside else "no water inside yet"
    return f"{rec.people or '?'} people. Can't leave alone: {needs}. {water.capitalize()}. Language: {rec.language}."


def house_card(rec: Record) -> str:
    """A <=40-word card a rescue crew reads before knocking."""
    facts = rec.model_dump(include={"people", "cant_leave_alone", "water_inside", "language"})
    prompt = (
        "Write a rescue crew's house card in at most 40 words, using only these facts: "
        f"{json.dumps(facts)}. Include people count, who can't leave and why, and the language. "
        "If someone uses a power wheelchair, note it can weigh about 400 lb and needs 2-3 lifters. "
        "If someone is bedbound, note a stretcher is needed. Plain text, no promises."
    )
    try:
        card = guard(ask(prompt, max_tokens=90))
    except Exception:
        card = ""
    return card or _card_fallback(rec)


def _counts(records: list[Record]) -> dict:
    counts: dict[str, int] = {}
    for rec in records:
        counts[rec.status] = counts.get(rec.status, 0) + 1
    return counts


def briefing(t_min: int, records: list[Record], ranked: list[dict] | None = None) -> str:
    """A <=60-word situation summary for the incident commander."""
    counts = _counts(records)
    top = [r["household_id"] + ": " + ", ".join(r.get("reasons", [])) for r in (ranked or [])[:3]]
    needs = [f"{p.get('who')} ({p.get('need')})" for rec in records for p in rec.cant_leave_alone][:6]
    prompt = (
        f"You brief a flood incident commander at minute {t_min}. In at most 60 words, summarize: "
        f"status counts {json.dumps(counts)}; top of rescue queue {top}; mobility needs {needs}. "
        "Mention no-answer homes need door knocks and neighbors with trucks/boats are available if any. "
        "Plain text, facts only, no promises."
    )
    try:
        text = guard(ask(prompt, max_tokens=120))
    except Exception:
        text = ""
    return text or (
        f"Minute {t_min}: {counts.get('needs_help', 0)} need help, {counts.get('can_help', 0)} can help, "
        f"{counts.get('safe', 0)} safe, {counts.get('no_answer', 0)} no answer (door-knock list)."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Qwen3-VL imagery check on the Harvey after-images.")
    parser.add_argument("--out", type=Path, default=Path("web/public/data"))
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    found = imagery_check(None, args.out, args.data_dir)
    print(f"{len(found)} images:", {v: sum(r['verdict'] == v for r in found) for v in ('flooded', 'not_flooded', 'uncertain')})
