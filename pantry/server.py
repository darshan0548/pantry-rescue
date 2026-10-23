"""Pantry Rescue: an MCP server (Streamable HTTP) for Alexa+ that tracks groceries
by expiry date and tells you what to cook before food goes to waste."""
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

HERE = Path(__file__).parent
BOARD_URI = "ui://pantry/board"
UI_META = {"ui": {"resourceUri": BOARD_URI}, "ui/resourceUri": BOARD_URI}

# Typical fridge/pantry shelf life in days (used when the user gives no date).
SHELF_DAYS = {
    "spinach": 4, "tomato": 6, "onion": 30, "potato": 21, "carrot": 14, "capsicum": 7,
    "cucumber": 6, "cauliflower": 7, "coriander": 4, "banana": 5, "apple": 14,
    "milk": 5, "curd": 6, "yogurt": 8, "paneer": 5, "cheese": 14, "butter": 30,
    "egg": 21, "bread": 4, "chicken": 2, "fish": 2, "rice": 365, "dal": 365,
}
DEFAULT_DAYS = 7

# name -> (ingredients, short method)
RECIPES = {
    "Palak paneer": (["spinach", "paneer", "onion", "tomato"],
                     "Blend blanched spinach, fry onion and tomato, add paneer and the puree."),
    "Veg omelette": (["egg", "onion", "tomato", "capsicum"],
                     "Whisk eggs, fold in chopped veg, cook on a medium pan."),
    "Aloo gobi": (["potato", "cauliflower", "onion", "tomato"],
                  "Saute onion and tomato, add spices, potato and cauliflower, cover and cook."),
    "Curd rice": (["rice", "curd", "cucumber", "carrot"],
                  "Mix cooked rice with curd, top with grated carrot and cucumber."),
    "Paneer bhurji": (["paneer", "onion", "tomato", "capsicum"],
                      "Crumble paneer and cook it with sauteed onion, tomato and capsicum."),
    "Banana pancakes": (["banana", "egg", "milk"],
                        "Mash bananas, whisk with egg and milk, cook small pancakes."),
    "Dal tadka": (["dal", "onion", "tomato", "coriander"],
                  "Pressure-cook dal, then add a tempering of onion, tomato and coriander."),
    "Chicken curry": (["chicken", "onion", "tomato", "potato"],
                      "Brown onions, add tomato and spices, then chicken and potato."),
}

mcp = FastMCP(
    "pantry-rescue",
    instructions=("Pantry Rescue tracks groceries by expiry date. Use it when the user says "
                  "they bought food, asks what is about to expire, what to cook, or says "
                  "they used something up."),
    host="0.0.0.0", stateless_http=True, json_response=True,
)


# ---------------------------------------------------------------- storage
def today() -> date:
    return date.today()


def db() -> sqlite3.Connection:
    con = sqlite3.connect(os.getenv("PANTRY_DB", "pantry.db"))
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, added TEXT NOT NULL,
        expires TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', used_on TEXT)""")
    con.execute("UPDATE items SET status='expired' WHERE status='active' AND expires < ?",
                (today().isoformat(),))
    return con


def norm(name: str) -> str:
    n = name.strip().lower()
    if n.endswith("oes"):
        return n[:-2]
    if n.endswith("s") and not n.endswith("ss") and len(n) > 3:
        return n[:-1]
    return n


def active() -> list[dict[str, Any]]:
    with db() as con:
        rows = con.execute("SELECT name, expires FROM items WHERE status='active' "
                           "ORDER BY expires, name").fetchall()
    return [{"name": r["name"], "expires": r["expires"],
             "days_left": (date.fromisoformat(r["expires"]) - today()).days} for r in rows]


def say_list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def days_word(d: int) -> str:
    return "today" if d == 0 else "tomorrow" if d == 1 else f"in {d} days"


# ---------------------------------------------------------------- tools
@mcp.tool()
def add_items(items: list[str], days_until_expiry: int | None = None) -> dict[str, Any]:
    """Use when the user says they bought, got or brought home groceries.
    items: food names, e.g. ["spinach", "paneer"]. days_until_expiry: only if the user
    states it; otherwise typical shelf life is used per item."""
    added = []
    with db() as con:
        for raw in items:
            name = norm(raw)
            if not name:
                continue
            days = days_until_expiry if days_until_expiry is not None else SHELF_DAYS.get(name, DEFAULT_DAYS)
            exp = today() + timedelta(days=max(days, 0))
            con.execute("INSERT INTO items(name, added, expires) VALUES (?,?,?)",
                        (name, today().isoformat(), exp.isoformat()))
            added.append({"name": name, "expires": exp.isoformat(), "days_left": days})
    if not added:
        return {"speech": "I didn't catch any items to add.", "added": []}
    first = min(added, key=lambda a: a["days_left"])
    return {"speech": f"Added {say_list([a['name'] for a in added])}. "
                      f"{first['name'].capitalize()} will go off first, {days_word(first['days_left'])}.",
            "added": added}


@mcp.tool()
def list_expiring(within_days: int = 3) -> dict[str, Any]:
    """Use when the user asks what is about to go bad, expire, or what needs eating soon."""
    soon = [i for i in active() if i["days_left"] <= within_days]
    if not soon:
        return {"speech": f"Nothing expires in the next {within_days} days. Your pantry is in good shape.",
                "items": []}
    parts = [f"{i['name']} {days_word(i['days_left'])}" for i in soon[:5]]
    return {"speech": f"{len(soon)} item{'s' if len(soon) > 1 else ''} to use soon: {say_list(parts)}.",
            "items": soon}


def _bedrock_idea(names: list[str]) -> str | None:
    model = os.getenv("PANTRY_BEDROCK_MODEL")  # optional AWS Builder integration
    if not model:
        return None
    try:
        import boto3
        out = boto3.client("bedrock-runtime").converse(
            modelId=model, inferenceConfig={"maxTokens": 150},
            messages=[{"role": "user", "content": [{"text":
                f"In two sentences, suggest one quick dinner using: {', '.join(names)}."}]}])
        return out["output"]["message"]["content"][0]["text"].strip()
    except Exception:
        return None


@mcp.tool()
def suggest_meal() -> dict[str, Any]:
    """Use when the user asks what to cook, eat or make tonight. Ranks recipes by how
    much soon-to-expire food they use up."""
    stock = {i["name"]: i for i in active()}
    ranked = []
    for title, (ings, method) in RECIPES.items():
        have = [g for g in ings if g in stock]
        if len(have) < 2:
            continue
        score = sum(max(1, 6 - stock[g]["days_left"]) for g in have)
        ranked.append({"recipe": title, "uses": have, "missing": [g for g in ings if g not in stock],
                       "method": method, "score": score})
    ranked.sort(key=lambda r: -r["score"])
    if not ranked:
        idea = _bedrock_idea(list(stock)) if stock else None
        return {"speech": idea or "I need at least two matching ingredients to suggest a meal. "
                                  "Tell me what you have bought.", "options": []}
    top = ranked[:2]
    best = top[0]
    miss = f" You are missing {say_list(best['missing'])}." if best["missing"] else ""
    return {"speech": f"Cook {best['recipe']} tonight. It uses up {say_list(best['uses'])}.{miss} {best['method']}",
            "options": top, "ai_idea": _bedrock_idea(best["uses"])}


@mcp.tool()
def mark_used(item: str) -> dict[str, Any]:
    """Use when the user says they used, cooked, ate, finished or threw out an item."""
    name = norm(item)
    with db() as con:
        row = con.execute("SELECT id FROM items WHERE status='active' AND name=? "
                          "ORDER BY expires LIMIT 1", (name,)).fetchone()
        if not row:
            return {"speech": f"I couldn't find {name} in your pantry.", "ok": False}
        con.execute("UPDATE items SET status='used', used_on=? WHERE id=?",
                    (today().isoformat(), row["id"]))
    return {"speech": f"Done. {name.capitalize()} is marked as used, and that's one less thing wasted.",
            "ok": True}


@mcp.tool()
def weekly_summary() -> dict[str, Any]:
    """Use when the user asks how they are doing, how much food they saved or wasted this week."""
    since = (today() - timedelta(days=7)).isoformat()
    with db() as con:
        saved = con.execute("SELECT COUNT(*) FROM items WHERE status='used' AND used_on>=?", (since,)).fetchone()[0]
        wasted = con.execute("SELECT COUNT(*) FROM items WHERE status='expired' AND expires>=?", (since,)).fetchone()[0]
    total = saved + wasted
    rate = round(100 * saved / total) if total else 100
    return {"speech": f"This week you used {saved} item{'s' if saved != 1 else ''} in time and "
                      f"{wasted} expired. That's a {rate} percent rescue rate.",
            "saved": saved, "wasted": wasted, "rescue_rate": rate}


@mcp.tool(meta=UI_META)
def show_pantry_board() -> dict[str, Any]:
    """Use when the user asks to see, show or display their pantry or what is in the fridge."""
    items = active()
    urgent = sum(1 for i in items if i["days_left"] <= 2)
    return {"speech": f"You have {len(items)} items. {urgent} need attention in the next two days.",
            "items": items, "summary": weekly_summary()}


@mcp.resource(BOARD_URI, mime_type="text/html;profile=mcp-app", meta={"ui": {"prefersBorder": False}})
def board_ui() -> str:
    return (HERE / "board.html").read_text(encoding="utf-8")


@mcp.custom_route("/sim", methods=["GET"])
async def sim_page(_: Request) -> HTMLResponse:
    """Voice simulator: a stand-in Alexa+ host that talks to /mcp."""
    return HTMLResponse((HERE / "sim.html").read_text(encoding="utf-8"))


@mcp.custom_route("/sim/board", methods=["GET"])
async def sim_board(_: Request) -> HTMLResponse:
    return HTMLResponse((HERE / "board.html").read_text(encoding="utf-8"))


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------- app
class TokenAuth:
    """Bearer-token guard. Active only when PANTRY_TOKEN is set; /health stays open."""

    def __init__(self, app):
        self.app, self.token = app, os.getenv("PANTRY_TOKEN")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.token and scope["path"] != "/health" and not scope["path"].startswith("/sim"):
            auth = dict(scope["headers"]).get(b"authorization", b"").decode()
            if auth != f"Bearer {self.token}":
                return await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
        await self.app(scope, receive, send)


def build_app():
    return TokenAuth(mcp.streamable_http_app())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
