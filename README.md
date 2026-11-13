# Swift

When a flood threatens a neighborhood, Swift's AI agent phones every household, in the order the water is predicted to reach them. It records who needs help getting out, who can help (a truck, a boat, free seats) and who never picked up. Dispatchers see it all on one map, with rescue routes that avoid streets too deep for each vehicle and a door-knock list for the homes that stayed silent.

The language model behind every call is Qwen3-VL served from the organizers' Dell Pro Max GB10 cluster: it holds the live phone conversations, labels the Harvey aerial photos, writes responder house cards and briefs the incident commander. The flood-depth model, routing and simulations run alongside it on our laptops.

## Repo layout
| Path | What |
|---|---|
| `CONTRACT.md` | The data contract between the backend and the dashboard. **Read this first.** |
| `web/` | Dashboard (React + deck.gl). Reads `web/public/data/` |
| `web/public/data/` | Fixture files (sample data now; the pipeline overwrites them) |
| `pipeline/` | Flood depth, call schedule, routing, Monte Carlo (Python) |
| `agent/` | Call script, Retell custom-LLM server, simulated residents |
| `tests/` | Small pytest suite |

## Frontend quick start (teammate)
```bash
cd web            # scaffold already in repo? if not: npm create vite@latest web -- --template react-ts  (choose "Ignore files and continue")
npm install
npm run dev
```
Build against `web/public/data/` only. Leave `VITE_API_URL` empty until integration.

## Backend quick start (Eric)
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[geo]" pytest
cp .env.example .env            # model server defaults are filled in; add Retell + phone numbers
.venv/bin/pytest -q
.venv/bin/uvicorn agent.server:app --port 8080
cloudflared tunnel --url http://localhost:8080   # paste the URL into Retell (WebSocket + webhook) and PUBLIC_URL
```
The model server (`http://10.246.100.230/v1`) is only reachable on the venue network that routes to `10.246.x.x`.

_More (problem, results, how it works in a real event) coming._
