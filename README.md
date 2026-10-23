# Pantry Rescue

Voice-first food-waste tracker for **Alexa+**. Say what you bought; it tracks expiry dates,
tells you what to cook tonight to use the most urgent items, and shows an expiry board on screen.

Built for the Amazon Developer Hackathon 2026 (Alexa+ track): a self-hosted **MCP server**,
spec 2025-11-25, **Streamable HTTP** at `/mcp`, with an **MCP Apps** widget (`ui://pantry/board`).

## Tools
| Tool | Triggered by |
|---|---|
| `add_items` | "I bought spinach and paneer" |
| `list_expiring` | "What's about to go bad?" |
| `suggest_meal` | "What should I cook tonight?" |
| `mark_used` | "I used the paneer" |
| `weekly_summary` | "How much food did I save?" |
| `show_pantry_board` | "Show my pantry" (renders the widget) |

## Run
```bash
pip install -r requirements.txt
python -m pantry.server          # http://localhost:8000/mcp
python -m pytest -q              # 6 tests
```
Env: `PORT`, `PANTRY_DB` (sqlite path), `PANTRY_TOKEN` (enables bearer auth),
`PANTRY_BEDROCK_MODEL` (optional: AWS Bedrock model id for extra meal ideas; needs `boto3`).

Deploy: `docker build -t pantry . && docker run -p 8000:8000 -v pantry:/data pantry`
(Render / Fly.io / Cloud Run all work; you need a public HTTPS URL for `/mcp`).

## Voice simulator (no device needed)
Open `http://localhost:8000/sim`. Type or speak ("I bought spinach and paneer"); the page sends
each request to the real MCP endpoint `/mcp`, speaks the reply, and renders the MCP App board in a
frame, acting as a minimal MCP Apps host. Run without `PANTRY_TOKEN` when demoing the simulator.

## Register with Alexa+
Create an Alexa+ MCP add-on pointing at `https://<your-host>/mcp` using the add-on Agent Skill
or the Alexa AI CLI, then run `alexa-ai deploy`. Follow the hackathon's Alexa+ track resources
for the exact commands and auth settings, and redeploy after any tool change.

## Design notes
- Tool descriptions are written as triggers ("Use when the user says...") so Alexa+ routes well.
- Every tool returns a short `speech` string plus structured data for the widget.
- Stateless HTTP (no session ids), SQLite storage, expiry computed lazily on every request.

MIT licensed.
