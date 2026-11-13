# Swift

When a flood threatens a neighborhood, Swift's AI agent phones every household, in the order the water is predicted to reach them. It records who needs help getting out, who can help (a truck, a boat, free seats) and who never picked up. Dispatchers see it all on one map, with rescue routes that avoid streets too deep for each vehicle and a door-knock list for the homes that stayed silent.

Everything runs on a Dell Pro Max GB10: the language model behind every call, the flood-depth model, routing and the simulations.

## Repo layout
| Path | What |
|---|---|
| `CONTRACT.md` | The data contract between the backend and the dashboard. **Read this first.** |
| `web/` | Dashboard (React + deck.gl). Reads `web/public/data/` |
| `web/public/data/` | Fixture files (sample data now; the pipeline overwrites them) |
| `pipeline/` | Flood depth, call schedule, routing, Monte Carlo (Python, GPU on the GB10) |
| `agent/` | Call script, Retell custom-LLM server, simulated residents |
| `tests/` | Small pytest suite |

## Frontend quick start (teammate)
```bash
cd web            # scaffold already in repo? if not: npm create vite@latest web -- --template react-ts  (choose "Ignore files and continue")
npm install
npm run dev
```
Build against `web/public/data/` only. Leave `VITE_API_URL` empty until integration.

_More (problem, results, how it works in a real event) coming._
