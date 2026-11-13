import asyncio
import json
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from relay import client
from relay.app import app as relay_app

SECRET = "test-secret"
local = FastAPI()
webhooks: list = []


@local.websocket("/llm-websocket/{call_id}")
async def echo(ws: WebSocket, call_id: str):
    await ws.accept()
    await ws.send_text(json.dumps({"response_type": "config", "call_id": call_id}))
    try:
        while True:
            message = json.loads(await ws.receive_text())
            await ws.send_text(json.dumps({"echo": message, "call_id": call_id}))
    except WebSocketDisconnect:
        pass


@local.post("/retell/webhook")
async def webhook(request: Request):
    webhooks.append(await request.json())
    return {"ok": True}


def _serve(app) -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    return f"http://127.0.0.1:{port}"


@pytest.fixture(scope="module")
def urls():
    os.environ["RELAY_SECRET"] = SECRET
    return _serve(relay_app), _serve(local)


async def _wait_for_agent(relay_url: str) -> None:
    async with httpx.AsyncClient() as http:
        for _ in range(100):
            if (await http.get(f"{relay_url}/health")).json()["agent_connected"]:
                return
            await asyncio.sleep(0.05)
    raise AssertionError("relay client never connected")


def test_relay_round_trip(urls):
    relay_url, local_url = urls

    async def scenario():
        agent = asyncio.create_task(client.run(relay_url, SECRET, local_url))
        try:
            await _wait_for_agent(relay_url)
            ws_base = relay_url.replace("http://", "ws://")
            async with connect(f"{ws_base}/llm-websocket/call-1") as a, connect(f"{ws_base}/llm-websocket/call-2") as b:
                assert json.loads(await a.recv()) == {"response_type": "config", "call_id": "call-1"}
                assert json.loads(await b.recv()) == {"response_type": "config", "call_id": "call-2"}
                await a.send(json.dumps({"interaction_type": "response_required", "response_id": 1}))
                await b.send(json.dumps({"interaction_type": "ping_pong"}))
                assert json.loads(await b.recv())["call_id"] == "call-2"
                assert json.loads(await a.recv()) == {
                    "echo": {"interaction_type": "response_required", "response_id": 1}, "call_id": "call-1"}
            async with httpx.AsyncClient() as http:
                r = await http.post(f"{relay_url}/retell/webhook", json={"event": "call_ended", "call": {"call_id": "x"}})
                assert r.status_code == 200
            for _ in range(100):
                if webhooks:
                    break
                await asyncio.sleep(0.02)
            assert webhooks == [{"event": "call_ended", "call": {"call_id": "x"}}]
        finally:
            agent.cancel()

    asyncio.run(scenario())


def test_relay_rejects_bad_token(urls):
    relay_url, _ = urls

    async def scenario():
        with pytest.raises(InvalidStatus):
            async with connect(f"{relay_url.replace('http://', 'ws://')}/agent?token=wrong"):
                pass

    asyncio.run(scenario())
