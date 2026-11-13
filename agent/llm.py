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
    "cant_leave": {"cant_leave_alone": {"type": "array", "items": PERSON}},
    "water_inside": {"water_inside": {"type": "boolean"}},
    "can_help": {"truck": {"type": "boolean"}, "boat": {"type": "boolean"}, "seats": {"type": "integer"}},
    "readback": {"correct": {"type": "boolean"}, "people": {"type": "integer"},
                 "cant_leave_alone": {"type": "array", "items": PERSON}, "water_inside": {"type": "boolean"}},
    "close": {},
}
QUESTIONS = {
    "confirm_address": "whether this is the right address, and the language they speak (en or es)",
    "people": "how many people are at the home (and anyone mentioned who can't leave alone)",
    "cant_leave": "who can't leave on their own and why (wheelchair: say manual or power; oxygen; bedbound). Empty list if nobody",
    "water_inside": "whether water is inside the home",
    "can_help": "whether they have a high-clearance truck, a boat, or free seats",
    "readback": "whether the read-back was correct, plus any corrected facts",
    "close": "nothing",
}
SYSTEM = (
    "You extract facts from one turn of a flood-safety phone call. Use only what the caller said; "
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
    props = {key: _nullable(prop) for key, prop in STEP_FIELDS[step].items()}
    props["ack"] = {"type": "string"}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _template(step: str) -> str:
    keys = [f'"{key}": ' + ('[{"who": ..., "need": ...}]' if prop.get("type") == "array" else "...")
            for key, prop in STEP_FIELDS[step].items()]
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
    fields = {k: v for k, v in data.items() if k in STEP_FIELDS[step] and v is not None}
    if "cant_leave_alone" in fields:
        fields["cant_leave_alone"] = _real_people(fields["cant_leave_alone"])
    help_keys = {k: fields.pop(k) for k in ("truck", "boat", "seats") if k in fields}
    if help_keys:
        fields["can_help"] = help_keys
    ack = data.get("ack") if isinstance(data.get("ack"), str) else ""
    return fields, ack.strip()


def _real_people(people) -> list[dict]:
    """Drop entries the model filled with placeholders like "null" or an empty need."""
    if not isinstance(people, list):
        return []
    blank = {"", "null", "none", "n/a", "unknown", "no", "nothing", "nobody", "help", "assistance", "a ride",
             "ride", "boat", "truck", "car", "transportation", "evacuation", "evacuate", "leaving"}
    return [{"who": p["who"].strip(), "need": p["need"].strip()} for p in people
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
