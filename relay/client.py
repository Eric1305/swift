"""Laptop side of the Render relay: one outbound wss to the relay, fanned out to the local Swift server.

    .venv/bin/python -m relay.client          # reads RELAY_URL and RELAY_SECRET from .env

RELAY_URL is the relay's base URL (https://<app>.onrender.com); LOCAL_URL defaults to http://localhost:8080.
"""
import asyncio
import json
import os
from pathlib import Path

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

ROOT = Path(__file__).resolve().parents[1]
KEEPALIVE_S = 20


def _load_env(path: Path) -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def _ws_url(base: str) -> str:
    return base.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)


async def _pipe_call(call_id: str, inbox: asyncio.Queue, relay, local_url: str) -> None:
    """One Retell call: frames from the relay go to the local websocket and back, until either side closes."""
    try:
        async with connect(f"{_ws_url(local_url)}/llm-websocket/{call_id}") as local:
            async def downstream():
                while (data := await inbox.get()) is not None:
                    await local.send(data)
                await local.close()

            async def upstream():
                async for data in local:
                    await relay.send(json.dumps({"type": "msg", "call_id": call_id, "data": data}))

            done, pending = await asyncio.wait([asyncio.create_task(downstream()), asyncio.create_task(upstream())],
                                               return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except (OSError, ConnectionClosed) as exc:
        print(f"[relay] call {call_id}: local socket failed: {exc!r}", flush=True)
    try:
        await relay.send(json.dumps({"type": "close", "call_id": call_id}))
    except ConnectionClosed:
        pass


async def _keepalive(relay) -> None:
    # App-level traffic so Render's free tier never sees the service as idle.
    while True:
        await asyncio.sleep(KEEPALIVE_S)
        await relay.send(json.dumps({"type": "ping"}))


async def serve_once(relay_url: str, secret: str, local_url: str) -> None:
    calls: dict[str, tuple[asyncio.Queue, asyncio.Task]] = {}
    async with connect(f"{_ws_url(relay_url)}/agent?token={secret}", ping_interval=KEEPALIVE_S) as relay, \
            httpx.AsyncClient(timeout=15) as http:
        print(f"[relay] connected to {relay_url}, forwarding to {local_url}", flush=True)
        keepalive = asyncio.create_task(_keepalive(relay))
        try:
            async for raw in relay:
                frame = json.loads(raw)
                kind, call_id = frame.get("type"), frame.get("call_id", "")
                if kind == "open":
                    print(f"[relay] call {call_id} opened", flush=True)
                    inbox: asyncio.Queue = asyncio.Queue()
                    calls[call_id] = (inbox, asyncio.create_task(_pipe_call(call_id, inbox, relay, local_url)))
                elif kind == "msg" and call_id in calls:
                    calls[call_id][0].put_nowait(frame["data"])
                elif kind == "close" and call_id in calls:
                    print(f"[relay] call {call_id} closed", flush=True)
                    calls.pop(call_id)[0].put_nowait(None)
                elif kind == "webhook":
                    try:
                        await http.post(f"{local_url.rstrip('/')}/retell/webhook", content=frame["body"],
                                        headers={"content-type": "application/json"})
                    except httpx.HTTPError as exc:
                        print(f"[relay] webhook forward failed: {exc!r}", flush=True)
        finally:
            keepalive.cancel()
            for _, task in calls.values():
                task.cancel()


async def run(relay_url: str, secret: str, local_url: str) -> None:
    backoff = 1
    while True:
        try:
            await serve_once(relay_url, secret, local_url)
            backoff = 1
        except (OSError, ConnectionClosed) as exc:
            print(f"[relay] disconnected ({exc!r}); retrying in {backoff}s", flush=True)
        except Exception as exc:  # e.g. 403 bad token, or Render cold start returning 5xx
            print(f"[relay] connect failed ({exc!r}); retrying in {backoff}s", flush=True)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)


def main() -> None:
    _load_env(ROOT / ".env")
    asyncio.run(run(os.environ["RELAY_URL"], os.environ["RELAY_SECRET"],
                    os.environ.get("LOCAL_URL", "http://localhost:8080")))


if __name__ == "__main__":
    main()
