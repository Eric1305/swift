"""Public relay on Render: Retell can't reach the laptop through the venue firewall, but the laptop can reach us.

Retell --wss--> /llm-websocket/{call_id} --+
Retell --https--> /retell/webhook ---------+--> /agent <--wss (outbound from laptop)-- relay.client --> localhost:8080

Frames on /agent are JSON: {"type": "open"|"msg"|"close", "call_id", "data"?}, {"type": "webhook", "body"},
{"type": "ping"|"pong"}. The relay keeps no call state beyond which Retell socket belongs to which call_id.
"""
import asyncio
import json
import os
import secrets

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

app = FastAPI(title="Swift relay")

agent: dict = {"ws": None, "lock": asyncio.Lock()}
retell: dict[str, WebSocket] = {}


async def to_agent(frame: dict) -> bool:
    ws = agent["ws"]
    if ws is None:
        return False
    try:
        async with agent["lock"]:
            await ws.send_text(json.dumps(frame))
        return True
    except Exception:
        return False


@app.websocket("/agent")
async def agent_socket(ws: WebSocket, token: str = ""):
    expected = os.environ.get("RELAY_SECRET", "")
    if not expected or not secrets.compare_digest(token, expected):
        await ws.close(code=1008)
        return
    await ws.accept()
    if agent["ws"] is not None:  # a reconnecting laptop replaces its stale connection
        try:
            await agent["ws"].close()
        except Exception:
            pass
    agent["ws"] = ws
    try:
        while True:
            frame = json.loads(await ws.receive_text())
            kind, call = frame.get("type"), retell.get(frame.get("call_id", ""))
            if kind == "ping":
                await to_agent({"type": "pong"})
            elif kind == "msg" and call:
                try:
                    await call.send_text(frame["data"])
                except Exception:
                    pass
            elif kind == "close" and call:
                retell.pop(frame["call_id"], None)
                try:
                    await call.close()
                except Exception:
                    pass
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if agent["ws"] is ws:
            agent["ws"] = None
            # Retell auto-reconnects these once the laptop is back.
            for call_id, call in list(retell.items()):
                retell.pop(call_id, None)
                try:
                    await call.close(code=1011)
                except Exception:
                    pass


@app.websocket("/llm-websocket/{call_id}")
async def llm_websocket(ws: WebSocket, call_id: str):
    if agent["ws"] is None:
        await ws.close(code=1011)
        return
    await ws.accept()
    retell[call_id] = ws
    await to_agent({"type": "open", "call_id": call_id})
    try:
        while True:
            await to_agent({"type": "msg", "call_id": call_id, "data": await ws.receive_text()})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if retell.get(call_id) is ws:
            retell.pop(call_id, None)
            await to_agent({"type": "close", "call_id": call_id})


@app.post("/retell/webhook")
async def retell_webhook(request: Request):
    await to_agent({"type": "webhook", "body": (await request.body()).decode()})
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True, "agent_connected": agent["ws"] is not None, "calls": len(retell)}
