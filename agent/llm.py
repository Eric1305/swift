"""Calls to Qwen on the GB10 (vLLM, OpenAI-compatible)."""
import base64
import json
import mimetypes
import os
import re
import threading
import time
from pathlib import Path

from openai import OpenAI

# Organizer-hosted Qwen3-VL on the GB10 cluster (OpenAI-compatible). Override with env vars.
BASE_URL = os.environ.get("VLLM_BASE_URL", "http://10.246.100.230/v1")
MODEL = os.environ.get("VLLM_MODEL", "qwen3-vl-8b-instruct")
API_KEY = os.environ.get("VLLM_API_KEY", "usaadatathon")
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}

PERSON = {"type": "object", "properties": {"who": {"type": "string"}, "need": {"type": "string"}},
          "required": ["who", "need"]}
STEP_FIELDS = {
    "confirm_address": {"confirmed": {"type": "boolean"}, "language": {"type": "string", "enum": ["en", "es"]}},
    "people": {"people": {"type": "integer"}},
    "cant_leave": {"someone": {"type": "boolean"}, "cant_leave_alone": {"type": "array", "items": PERSON}},
    "water_inside": {"water_inside": {"type": "boolean"}},
    "can_help": {"truck": {"type": "boolean"}, "boat": {"type": "boolean"}, "seats": {"type": "integer"}},
    "readback": {"correct": {"type": "boolean"}, "people": {"type": "integer"},
                 "cant_leave_alone": {"type": "array", "items": PERSON}, "water_inside": {"type": "boolean"}},
    "fix": {"people": {"type": "integer"}, "cant_leave_alone": {"type": "array", "items": PERSON},
            "water_inside": {"type": "boolean"}, "truck": {"type": "boolean"}, "boat": {"type": "boolean"},
            "seats": {"type": "integer"}},
    "close": {},
}
STEP_FIELDS["cant_leave_detail"] = STEP_FIELDS["cant_leave"]
# Facts residents volunteer out of turn ("me and my mom, she uses a power wheelchair") are captured on any step.
VOLUNTEERED = {"people": {"type": "integer"}, "cant_leave_alone": {"type": "array", "items": PERSON}}


def step_fields(step: str) -> dict:
    return {} if step == "close" else {**VOLUNTEERED, **STEP_FIELDS[step]}
QUESTIONS = {
    "confirm_address": "whether this is the right address, and the language they speak (en or es)",
    "people": "how many people are at the home (and anyone mentioned who can't leave alone)",
    "cant_leave": ("whether anyone can't leave on their own ('someone': true/false) and, only if the caller named them, "
                   "who and why. A bare 'yes' means someone=true with an empty list"),
    "cant_leave_detail": "who can't leave on their own and what they need to get out",
    "fix": "what was wrong in our read-back; return only the corrected facts",
    "water_inside": "whether water is inside the home",
    "can_help": "whether they have a high-clearance truck, a boat, or free seats",
    "readback": "whether the read-back was correct, plus any corrected facts",
    "close": "nothing",
}
SYSTEM = (
    "You extract facts from one turn of a flood-safety phone call. Use only words the caller actually said; never "
    "copy examples or options from our question (a bare 'yes' names nobody and no condition). "
    "use null for anything the caller did not answer. Also write 'ack': a warm acknowledgment of at most 12 words. "
    "Never promise help, rescue, or safety; never say the caller is safe or that anyone is coming. Reply with JSON only."
)


def _client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=30, max_retries=0)


STATS = {"in_flight": 0, "calls": 0, "latency_ms": 0.0}
_stats_lock = threading.Lock()


def _create(**kwargs):
    """Call the server (tracking in-flight calls and latency); if it rejects structured output or template
    kwargs, retry without them."""
    with _stats_lock:
        STATS["in_flight"] += 1
    started = time.perf_counter()
    try:
        return _create_once(**kwargs)
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        with _stats_lock:
            STATS["in_flight"] -= 1
            STATS["calls"] += 1
            STATS["latency_ms"] = round(0.8 * STATS["latency_ms"] + 0.2 * elapsed, 1) if STATS["calls"] > 1 else round(elapsed, 1)


def _create_once(**kwargs):
    client = _client()
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        if "response_format" not in kwargs and "extra_body" not in kwargs:
            raise
        status = getattr(exc, "status_code", None)
        if status not in (400, 422):
            raise
        kwargs.pop("response_format", None)
        kwargs.pop("extra_body", None)
        return client.chat.completions.create(**kwargs)


def _nullable(prop: dict) -> dict:
    return prop if prop.get("type") == "array" else {**prop, "type": [prop["type"], "null"]}


def _schema(step: str) -> dict:
    """Every key is required (null = not answered): under structured output the model skips optional keys."""
    props = {key: _nullable(prop) for key, prop in step_fields(step).items()}
    props["ack"] = {"type": "string"}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _template(step: str) -> str:
    keys = [f'"{key}": ' + ('[{"who": ..., "need": ...}]' if prop.get("type") == "array" else "...")
            for key, prop in step_fields(step).items()]
    return "{" + ", ".join(keys + ['"ack": "..."']) + "}"


def extract(step: str, utterance: str) -> tuple[dict, str]:
    """Return (fields relevant to this step, short acknowledgment). Any failure returns ({}, "")."""
    if not utterance.strip():
        return {}, ""
    try:
        completion = _create(
            model=MODEL,
            temperature=0,
            max_tokens=150,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": (f"We asked about {QUESTIONS[step]}.\nCaller said: {utterance}\n"
                                             f"Reply with exactly these keys (null if not answered): {_template(step)}")},
            ],
            response_format={"type": "json_schema", "json_schema": {"name": step, "schema": _schema(step)}},
            extra_body=NO_THINKING,
        )
        text = completion.choices[0].message.content or ""
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0)) if match else None
    except Exception:
        return {}, ""
    if not isinstance(data, dict):
        return {}, ""
    fields = {k: v for k, v in data.items() if k in step_fields(step) and v is not None}
    people = [p for p in _grounded(_real_people(fields.pop("cant_leave_alone", [])), utterance) if _plausible(p)]
    if step not in ("cant_leave", "cant_leave_detail", "readback", "fix"):
        people = [p for p in people if MOBILITY.search(p["need"])]  # volunteered: only clear mobility/medical needs
    negative = bool(NEGATIVE.match(utterance.strip()))
    if step in ("cant_leave", "cant_leave_detail"):
        if negative and not people:
            fields.update(someone=False, cant_leave_alone=[])
        elif people:
            fields.update(someone=True, cant_leave_alone=people)
    elif people:
        fields["cant_leave_alone"] = people
    if step == "water_inside" and "water_inside" not in fields and negative:
        fields["water_inside"] = False
    if step == "readback" and "correct" not in fields and (negative or AFFIRMATIVE.match(utterance.strip())):
        fields["correct"] = not negative
    help_keys = {k: fields.pop(k) for k in ("truck", "boat", "seats") if k in fields}
    if step == "can_help" and not help_keys and negative:
        help_keys = {"truck": False, "boat": False, "seats": 0}
    if help_keys:
        fields["can_help"] = help_keys
    ack = data.get("ack") if isinstance(data.get("ack"), str) else ""
    return fields, ack.strip()


NEGATIVE = re.compile(r"^(no|nope|nah|not really|no,? (sorry|thanks|thank you|we don'?t|i don'?t|nobody|not yet)"
                      r"|nobody|none|no one|i don'?t|we don'?t)\b", re.I)
AFFIRMATIVE = re.compile(r"^(yes|yep|yeah|yup|correct|right|that'?s (right|correct)|sure|s[ií])\b", re.I)
STOPWORDS = {"the", "and", "who", "can", "can't", "cant", "has", "needs", "need", "uses", "use", "with", "her", "his",
             "she", "they", "them", "their", "on", "a", "an", "to", "of", "my", "our", "is", "be", "help", "leave"}


NEGATED = re.compile(r"\b(no|not|none|nobody|no one|nothing|don'?t|doesn'?t|fine|good|okay|ok)\b", re.I)
GROUP = re.compile(r"^(everyone|everybody|all of us|us|we|no one|nobody|me and|the (two|three|four|five)|\w+ of us)", re.I)
MOBILITY = re.compile(r"wheel ?chair|oxygen|bed ?bound|bedridden|walker|crutch|cane|can'?t walk|cannot walk|stretcher|"
                      r"dialysis|disab|paraly|blind|deaf|hospice|surgery|injur|frail|dementia|mobility|silla de ruedas|"
                      r"ox[ií]geno|en cama|andadera|muletas", re.I)


def _plausible(person: dict) -> bool:
    """Reject chatty negatives the model turns into people ("everyone: no need", "us: no truck or boat")."""
    return not NEGATED.search(person["need"]) and not GROUP.match(person["who"])


def _grounded(people: list[dict], utterance: str) -> list[dict]:
    """Keep only people the caller actually described: some word of who/need must appear in what they said."""
    said = utterance.lower()
    kept = []
    for person in people:
        words = re.findall(r"[a-z']+", f"{person['who']} {person['need']}".lower())
        if any(len(w) >= 3 and w not in STOPWORDS and w.rstrip("s") in said for w in words):
            kept.append(person)
    return kept


def _real_people(people) -> list[dict]:
    """Drop entries the model filled with placeholders like "null" or an empty need."""
    if not isinstance(people, list):
        return []
    blank = {"", "null", "none", "n/a", "unknown", "no", "nothing", "nobody", "help", "assistance", "a ride",
             "ride", "boat", "truck", "car", "transportation", "evacuation", "evacuate", "leaving"}
    return [{"who": re.sub(r"^(my|our|the|his|her|their)\s+", "", p["who"].strip(), flags=re.I), "need": p["need"].strip()}
            for p in people
            if isinstance(p, dict) and isinstance(p.get("who"), str) and isinstance(p.get("need"), str)
            and p["who"].strip().lower() not in blank and p["need"].strip().lower() not in blank]


def _image_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode('ascii')}"


def ask(prompt: str, image_path: str | None = None, max_tokens: int = 300) -> str:
    """One free-form prompt (optionally with an image) to Qwen."""
    content: list[dict] = [{"type": "text", "text": prompt}]
    if image_path:
        content.append({"type": "image_url", "image_url": {"url": _image_url(image_path)}})
    completion = _create(
        model=MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
        extra_body=NO_THINKING,
    )
    return (completion.choices[0].message.content or "").strip()
