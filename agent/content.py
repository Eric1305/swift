"""LLM content on the GB10: Harvey imagery check, responder house cards, commander briefings."""
import argparse
import csv
import json
import os
import re
from pathlib import Path

from agent.llm import ask
from agent.script import Record, guard

DATA_DIR = Path(os.environ.get("SWIFT_DATA_DIR", Path.home() / "Texas_Flood_Student_Data"))

# Demo area: Bear Creek, west Houston (Addicks Reservoir backflow): dense homes + 21 georeferenced response images.
DEMO_BBOX = (-95.66, 29.835, -95.62, 29.865)  # (west, south, east, north)

IMAGERY_PROMPT = (
    "This is an aerial photo taken after Hurricane Harvey. Is floodwater visibly covering roads or land around "
    "houses? An ordinary river, pond or reservoir pool alone is not flooding. "
    'Reply JSON {"verdict":"flooded|not_flooded|uncertain","explanation":"<=20 words"}'
)


def _first_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _in_bbox(row: dict, bbox: tuple[float, float, float, float]) -> bool:
    try:
        lon, lat = float(row["longitude"]), float(row["latitude"])
    except (KeyError, ValueError):
        return False
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def _thumb(src: Path, dst: Path) -> None:
    from PIL import Image

    with Image.open(src) as image:
        image.convert("RGB").resize((512, 512)).save(dst, quality=85)


def imagery_check(image_ids: list[str] | None, out: Path, data_dir: Path = DATA_DIR,
                  bbox: tuple[float, float, float, float] = DEMO_BBOX, limit: int = 40) -> list[dict]:
    """Ask Qwen3-VL whether each Harvey response image in the demo area shows flooding.

    Writes imagery.json with each image's real footprint (for draping on the map) plus 512 px thumbs of the
    response image and its paired before image."""
    with open(data_dir / "image_metadata.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {r["image_id"]: r for r in rows}
    if image_ids is None:
        image_ids = [r["image_id"] for r in rows
                     if r.get("image_role") == "response" and r.get("georeferenced") == "true" and _in_bbox(r, bbox)][:limit]
    (out / "img").mkdir(parents=True, exist_ok=True)
    results = []
    for image_id in image_ids:
        row = by_id[image_id]
        thumb = out / "img" / f"{image_id}.jpg"
        _thumb(data_dir / row["image_path"], thumb)
        before = by_id.get(row.get("paired_image_id", ""))
        if before:
            _thumb(data_dir / before["image_path"], out / "img" / f"{before['image_id']}.jpg")
        try:
            data = _first_json(ask(IMAGERY_PROMPT, image_path=str(thumb), max_tokens=80))
        except Exception:
            data = {}
        verdict = data.get("verdict") if data.get("verdict") in ("flooded", "not_flooded", "uncertain") else "uncertain"
        results.append({
            "image_id": image_id,
            "lon": float(row["longitude"]),
            "lat": float(row["latitude"]),
            "bounds": [[float(row["west"]), float(row["south"])], [float(row["east"]), float(row["north"])]],
            "thumb": f"img/{image_id}.jpg",
            "before_thumb": f"img/{before['image_id']}.jpg" if before else None,
            "date": row.get("acquisition_date", ""),
            "rain_3d_mm": float(row["preceding_3d_precipitation_mm"] or 0),
            "verdict": verdict,
            "explanation": data.get("explanation", "No explanation returned."),
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
        "Write a rescue crew's house card in at most 35 words, using ONLY these facts and adding no new conditions: "
        f"{json.dumps(facts)}. Include the people count, who can't leave and why, water inside or not, and the language. "
        "Plain text, no promises."
    )
    try:
        card = guard(ask(prompt, max_tokens=90))
    except Exception:
        card = ""
    mentioned = " ".join(p.get("need", "") for p in rec.cant_leave_alone).lower()
    invented = [w for w in ("bedbound", "oxygen", "wheelchair", "walker", "stretcher", "dialysis")
                if w in card.lower() and w not in mentioned and not (w == "stretcher" and "bedbound" in mentioned)]
    if invented:
        card = ""
    if card and "power wheelchair" in mentioned and "lb" not in card:
        card += " Power chair: ~400 lb, bring 2-3 lifters."
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
