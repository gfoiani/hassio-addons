"""
Telegram Bot Relay – Render Service

Acts as the bridge between the user's Telegram and the HA trading bot running
on Raspberry Pi (which cannot be reached directly from the internet).

Architecture:
  User ─Telegram─► Render (this service)  ◄── polling ── HA Trading Bot
                          │
                          └──► POST /api/notify  ── Telegram message to user
                               GET  /api/commands ── pending commands
                               POST /api/command-result ── reply to user

Environment variables (set in Render dashboard):
  TELEGRAM_BOT_TOKEN  – from @BotFather
  RELAY_API_KEY       – shared secret with the HA trading bot (any random string)
  ALLOWED_CHAT_IDS    – comma-separated Telegram chat IDs that may send commands
                        (find yours by messaging @userinfobot)
  WEBHOOK_URL         – public URL of this Render service
                        e.g. https://trading-bot-relay.onrender.com
                        (leave empty to use long-polling instead)
"""

import os
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
RELAY_API_KEY: str = os.environ["RELAY_API_KEY"]
WEBHOOK_URL: str = os.environ.get("WEBHOOK_URL", "").rstrip("/")

_raw_ids = os.environ.get("ALLOWED_CHAT_IDS", "")
ALLOWED_CHAT_IDS: set[int] = set()
for _cid in _raw_ids.split(","):
    _cid = _cid.strip()
    if not _cid:
        continue
    try:
        ALLOWED_CHAT_IDS.add(int(_cid))
    except ValueError:
        print(
            f"[config] WARNING: ALLOWED_CHAT_IDS contains non-numeric value '{_cid}' – skipped.\n"
            f"         Find your chat ID by messaging @userinfobot on Telegram."
        )

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

# Commands waiting to be polled by the HA bot
command_queue: deque[dict] = deque(maxlen=200)

# All chat IDs that have interacted with the bot (used to broadcast notifications)
known_chat_ids: set[int] = set(ALLOWED_CHAT_IDS)


# ---------------------------------------------------------------------------
# Lifespan: register Telegram webhook on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    if WEBHOOK_URL:
        webhook_endpoint = f"{WEBHOOK_URL}/telegram/webhook"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{TELEGRAM_API}/setWebhook",
                json={"url": webhook_endpoint, "allowed_updates": ["message"]},
            )
            result = resp.json()
            if result.get("ok"):
                print(f"[startup] Telegram webhook registered: {webhook_endpoint}")
            else:
                print(f"[startup] Webhook registration failed: {result}")
    else:
        print("[startup] WEBHOOK_URL not set – webhook NOT registered.")
    yield


app = FastAPI(title="Trading Bot Telegram Relay", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Security dependency
# ---------------------------------------------------------------------------

async def _require_api_key(x_api_key: str = Header(...)):
    if x_api_key != RELAY_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

async def _send_message(chat_id: int, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )


async def _broadcast(text: str) -> None:
    """Send a message to every known/allowed chat."""
    for chat_id in known_chat_ids:
        await _send_message(chat_id, text)


# ---------------------------------------------------------------------------
# Telegram webhook – receives messages from users
# ---------------------------------------------------------------------------

_HELP_TEXT = (
    "<b>Day Trading Bot – Commands</b>\n\n"
    "/status  – Open positions and unrealized P&amp;L\n"
    "/halt    – Halt new position entries\n"
    "/resume  – Resume position entries\n"
    "/close <code>SYMBOL</code>  – Close a specific position (e.g. <code>/close AAPL.US</code>)\n"
    "/help    – Show this message"
)

_KNOWN_COMMANDS = {"status", "positions", "halt", "resume", "close", "help", "start"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    message = data.get("message", {})
    chat = message.get("chat", {})
    chat_id: Optional[int] = chat.get("id")
    text: str = message.get("text", "").strip()

    if not chat_id or not text or not text.startswith("/"):
        return {"ok": True}

    # Authorization check
    if ALLOWED_CHAT_IDS and chat_id not in ALLOWED_CHAT_IDS:
        await _send_message(chat_id, "⛔ <b>Unauthorized.</b>\nThis bot is private.")
        return {"ok": True}

    known_chat_ids.add(chat_id)

    # Parse command (strip the Telegram @BotName suffix if present)
    parts = text.split(maxsplit=1)
    raw_cmd = parts[0].lstrip("/").split("@")[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    if raw_cmd in ("help", "start"):
        await _send_message(chat_id, _HELP_TEXT)
        return {"ok": True}

    if raw_cmd in _KNOWN_COMMANDS:
        command_id = str(uuid.uuid4())[:8]
        command_queue.append({
            "id":        command_id,
            "command":   raw_cmd,
            "args":      args,
            "chat_id":   chat_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await _send_message(
            chat_id,
            f"⏳ Command <code>{raw_cmd}</code> queued (id: <code>{command_id}</code>) …",
        )
    else:
        await _send_message(chat_id, f"❓ Unknown command: <code>{raw_cmd}</code>\n\n{_HELP_TEXT}")

    return {"ok": True}


# ---------------------------------------------------------------------------
# REST API for the HA trading bot
# ---------------------------------------------------------------------------

@app.get("/api/commands", dependencies=[Depends(_require_api_key)])
async def get_commands():
    """
    Poll pending commands.
    Returns the full queue and clears it.
    Called by the HA trading bot every check_interval seconds.
    """
    cmds = list(command_queue)
    command_queue.clear()
    return {"commands": cmds}


@app.post("/api/notify", dependencies=[Depends(_require_api_key)])
async def receive_notification(request: Request):
    """
    Receive a notification from the HA trading bot and broadcast it to all users.
    Body: { "text": "HTML-formatted message" }
    """
    body = await request.json()
    text: str = body.get("text", "")
    if text:
        await _broadcast(text)
    return {"ok": True}


@app.post("/api/command-result", dependencies=[Depends(_require_api_key)])
async def receive_command_result(request: Request):
    """
    Receive the result of a command execution and send it to the originating user.
    Body: { "chat_id": 123456789, "text": "HTML-formatted result" }
    """
    body = await request.json()
    chat_id: Optional[int] = body.get("chat_id")
    text: str = body.get("text", "")
    if chat_id and text:
        await _send_message(int(chat_id), text)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "queue_size": len(command_queue),
        "known_chats": len(known_chat_ids),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
