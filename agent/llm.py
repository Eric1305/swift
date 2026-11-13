"""Calls to Qwen on the GB10 (vLLM, OpenAI-compatible)."""
import base64
import json
import mimetypes
import os
import re
from pathlib import Path

from openai import OpenAI

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}

PERSON = {"type": "object", "properties": {"who": {"type": "string"}, "need": {"type": "string"}},
          "required": ["who", "need"]}
STEP_FIELDS = {
    "confirm_address": {"confirmed": {"type": "boolean"}, "language": {"type": "string", "enum": ["en", "es"]}},
    "people": {"people": {"type": "integer"}, "cant_leave_alone": {"type": "array", "items": PERSON}},
    "cant_leave": {"cant_leave_alone": {"type": "array", "items": PERSON}},
    "water_inside": {"water_inside": {"type": "boolean"}},
    "can_help": {"can_help": {"type": "object", "properties": {
        "truck": {"type": "boolean"}, "boat": {"type": "boolean"}, "seats": {"type": "integer"}}}},
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
    "omit any key the caller did not answer. Also write 'ack': a warm acknowledgment of at most 12 words. "
    "Never promise help, rescue, or safety, and never say anyone is coming. Reply with JSON only."
)


def _client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key="NONE", timeout=20, max_retries=0)


def _schema(step: str) -> dict:
    props = {**STEP_FIELDS[step], "ack": {"type": "string"}}
    return {"type": "object", "properties": props, "required": ["ack"]}


def extract(step: str, utterance: str) -> tuple[dict, str]:
    """Return (fields relevant to this step, short acknowledgment). Any failure returns ({}, "")."""
    if not utterance.strip():
        return {}, ""
    try:
        completion = _client().chat.completions.create(
            model=MODEL,
            temperature=0,
            max_tokens=150,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"We asked about {QUESTIONS[step]}.\nCaller said: {utterance}"},
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
    ack = data.get("ack") if isinstance(data.get("ack"), str) else ""
    return fields, ack.strip()


def _image_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode('ascii')}"


def ask(prompt: str, image_path: str | None = None, max_tokens: int = 300) -> str:
    """One free-form prompt (optionally with an image) to Qwen."""
    content: list[dict] = [{"type": "text", "text": prompt}]
    if image_path:
        content.append({"type": "image_url", "image_url": {"url": _image_url(image_path)}})
    completion = _client().chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
        extra_body=NO_THINKING,
    )
    return (completion.choices[0].message.content or "").strip()
