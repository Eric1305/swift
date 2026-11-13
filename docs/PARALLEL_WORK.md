# Parallel work launched before the session handoff

Three background agents were started at the end of the previous session. Each works in its own git worktree and
pushes **only to its own branch**, never to `main`. Read `HANDOFF.txt` first, then use this file to pick up their work.

| Branch | What it contains | Merge when |
|---|---|---|
| `relay` | `relay/app.py` (Render relay: WS `/agent?token=`, WS `/llm-websocket/{call_id}`, POST `/retell/webhook`, GET `/health`), `relay/client.py` (`python -m relay.client` on the laptop, one outbound wss to the relay, pipes to `localhost:8080`), `render.yaml`, `relay/requirements.txt`, `tests/test_relay.py` (end-to-end, no network), `RELAY_URL`/`RELAY_SECRET` in `.env.example`, a "Relay" section appended to `HANDOFF.txt` | Tests pass. This unblocks the live Retell call; merge first |
| `web-fixes` | Frontend aligned with the **real** fixtures in `web/public/data/` and `CONTRACT.md` (null handling, field names, imagery `bounds`/`before_thumb`, model panel, live-call fallback). The commit message or agent report lists PLAN T1–T6 features still missing | `npm run build` passes in `web/` |
| `docs` | Submission `README.md` (sourced stats, how it works, where AI runs, data, results, real-event table, limitations) and `docs/PITCH.md` (3-minute script timed to Run Demo + 10–12 judge Q&As) | Read it first: drop any stat that isn't linked to a source |

## How to pick them up
```bash
cd ~/Coding/Personal/swift && git checkout main && git pull && git fetch --all
for b in relay web-fixes docs; do echo "== $b"; git log --oneline main..origin/$b; done   # see what landed
git merge --no-edit origin/relay && .venv/bin/pytest -q          # then web-fixes, then docs
(cd web && npm install && npm run build)
git push origin main
```
If a branch is missing or empty, that agent didn't finish: redo that task from the spec in `HANDOFF.txt`
(relay) or the brief above, rather than waiting on it.

**Expected conflicts:**
- `docs` rewrites `README.md`, and the `relay` agent appends to `HANDOFF.txt`.
- Keep both sides; in `README.md`, keep the docs branch's version and re-check its quick-start commands.

## After merging: the path to the live call
1. Render: New → Blueprint (or Web Service) from `Eric1305/swift`, using `render.yaml`. Set `RELAY_SECRET` to a random string.
2. Retell agent: LLM WebSocket URL `wss://<app>.onrender.com/llm-websocket`, webhook `https://<app>.onrender.com/retell/webhook`.
3. Laptop `.env`: `RELAY_URL=wss://<app>.onrender.com`, `RELAY_SECRET=<same string>`.
4. Run `.venv/bin/uvicorn agent.server:app --port 8080`, `.venv/bin/python -m relay.client`, `curl -X POST localhost:8080/api/demo-call`.
5. Answer with the rehearsal lines (HANDOFF.txt), then `curl localhost:8080/api/live` should show `needs_help`.
6. Serve the dashboard from the same server: `cd web && npm run build`, then open `http://localhost:8080/` and press Run Demo.

## Remaining after that
- Record a backup demo video, rehearse 3×, make the repo public at submission (`gh repo edit --visibility public --accept-visibility-change-consequences`).
- If Eric still has GB10 access: `tmux kill-session -t eric-data` and `gh auth logout` there.
