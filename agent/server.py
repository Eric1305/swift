"""Retell custom-LLM server + dashboard API, served from the GB10.

Retell handles the phone line, speech-to-text, turn-taking and the voice. Every reply is decided here:
the code-driven script picks the question, Qwen (on the GB10) only extracts facts and acknowledges.
"""
import asyncio
import json
import os
import re
import subprocess
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]


def _load_env(path: Path) -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


_load_env(ROOT / ".env")

from agent.llm import BASE_URL, extract  # noqa: E402  (after .env so VLLM_* are picked up)
from agent.script import INTRO, CallState, Record, advance, prompt_for  # noqa: E402

DATA = ROOT / "web" / "public" / "data"
NO_ANSWER_REASONS = {"dial_no_answer", "dial_busy", "dial_failed", "voicemail_reached"}

app = FastAPI(title="Swift")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

calls: dict[str, CallState] = {}
live: dict = {"record": None, "call_status": "idle"}
simulation: dict = {"task": None}


def demo_household_id() -> str:
    return os.environ.get("DEMO_HOUSEHOLD_ID") or json.loads((DATA / "meta.json").read_text())["demo_household_id"]


def demo_state() -> CallState:
    household_id = demo_household_id()
    features = json.loads((DATA / "households.geojson").read_text())["features"]
    address = next((f["properties"]["address"] for f in features if f["properties"]["id"] == household_id), "")
    return CallState(record=Record(id=household_id, address=address, attempts=1))


def publish(state: CallState) -> None:
    live["record"] = state.record.model_dump(exclude={"address"})


def house_card(record: Record) -> str:
    try:
        from agent.content import house_card as llm_house_card  # Lane C; falls back until merged
        return llm_house_card(record)
    except Exception:
        needs = "; ".join(f"{p.get('who')}: {p.get('need')}" for p in record.cant_leave_alone) or "none reported"
        water = "water inside" if record.water_inside else "no water inside yet"
        return f"{record.people or '?'} people; can't leave alone: {needs}; {water}; language {record.language}."


@app.post("/api/demo-call")
async def demo_call():
    state = demo_state()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.retellai.com/v2/create-phone-call",
            headers={"Authorization": f"Bearer {os.environ['RETELL_API_KEY']}"},
            json={
                "from_number": os.environ["RETELL_FROM_NUMBER"],
                "to_number": os.environ["DEMO_PHONE"],
                "override_agent_id": os.environ["RETELL_AGENT_ID"],
                "metadata": {"household_id": state.record.id},
            },
        )
    response.raise_for_status()
    call_id = response.json()["call_id"]
    calls[call_id] = state
    live.update(call_status="ringing")
    publish(state)
    return {"call_id": call_id}


async def _send(ws: WebSocket, response_id: int, content: str, end_call: bool = False) -> None:
    await ws.send_json({"response_type": "response", "response_id": response_id, "content": content,
                        "content_complete": True, "end_call": end_call})


@app.websocket("/llm-websocket/{call_id}")
async def llm_websocket(ws: WebSocket, call_id: str):
    await ws.accept()
    state = calls.setdefault(call_id, demo_state())
    await ws.send_json({"response_type": "config", "config": {"auto_reconnect": True, "call_details": True}})
    opening = f"{INTRO} {prompt_for(state)}"
    state.record.transcript.append({"who": "agent", "text": opening})
    publish(state)
    await _send(ws, 0, opening)
    try:
        while True:
            message = await ws.receive_json()
            kind = message.get("interaction_type")
            if kind == "ping_pong":
                await ws.send_json({"response_type": "ping_pong", "timestamp": message.get("timestamp")})
            elif kind == "update_only":
                live["call_status"] = "in-progress"
            elif kind in ("response_required", "reminder_required"):
                live["call_status"] = "in-progress"
                fields, ack = {}, ""
                if kind == "response_required":
                    said = next((t["content"] for t in reversed(message.get("transcript", []))
                                 if t.get("role") == "user"), "")
                    if said:
                        state.record.transcript.append({"who": "resident", "text": said})
                    fields, ack = await run_in_threadpool(extract, state.step, said)
                state, reply = advance(state, fields, ack)
                done = state.step == "close"
                if done and state.record.status == "needs_help":
                    state.record.house_card = await run_in_threadpool(house_card, state.record)
                state.record.transcript.append({"who": "agent", "text": reply})
                calls[call_id] = state
                publish(state)
                await _send(ws, message["response_id"], reply, end_call=done)
    except WebSocketDisconnect:
        pass


@app.post("/retell/webhook")
async def retell_webhook(request: Request):
    body = await request.json()
    if body.get("event") == "call_ended":
        call = body.get("call", {})
        state = calls.get(call.get("call_id", ""))
        if call.get("disconnection_reason") in NO_ANSWER_REASONS:
            live["call_status"] = "no-answer"
            if state:
                state.record.status = "no_answer"
                publish(state)
        else:
            live["call_status"] = "completed"
    return {"ok": True}


@app.get("/api/live")
async def api_live():
    return live


def _memory_gb() -> tuple[float, float]:
    """GB10 memory is unified, so nvidia-smi often reports it as N/A; fall back to /proc/meminfo."""
    info = dict(re.findall(r"(\w+):\s+(\d+)", Path("/proc/meminfo").read_text()))
    total, available = int(info["MemTotal"]) / 1048576, int(info["MemAvailable"]) / 1048576
    return round(total - available, 1), round(total, 1)


@app.get("/api/gpu")
async def api_gpu():
    stats = {"gpu_util": 0, "mem_used_gb": 0.0, "mem_total_gb": 0.0, "temp_c": 0, "llm_running": 0}
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3).stdout
        util, used, total, temp = [v.strip() for v in out.splitlines()[0].split(",")]
        stats["gpu_util"], stats["temp_c"] = int(util), int(temp)
        if used.replace(".", "").isdigit():
            stats["mem_used_gb"], stats["mem_total_gb"] = round(float(used) / 1024, 1), round(float(total) / 1024, 1)
        else:
            stats["mem_used_gb"], stats["mem_total_gb"] = _memory_gb()
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            metrics = (await client.get(BASE_URL.removesuffix("/v1") + "/metrics")).text
        stats["llm_running"] = int(sum(float(v) for v in re.findall(r"^vllm:num_requests_running\{[^}]*\}\s+([\d.]+)", metrics, re.M)))
    except Exception:
        pass
    return stats


@app.post("/api/simulate-live")
async def simulate_live():
    if simulation["task"] and not simulation["task"].done():
        return {"started": True}
    try:
        from agent.simulate import simulate_all  # Lane C
    except Exception:
        return {"started": False}
    households = json.loads((DATA / "households.geojson").read_text())
    simulation["task"] = asyncio.create_task(
        run_in_threadpool(simulate_all, households, Path("/tmp/hg_live")))
    return {"started": True}


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="dashboard")
