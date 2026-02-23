"""
TelegramNotifier – HTTP client for the Telegram relay service on Render.

The HA trading bot (Raspberry Pi) cannot be reached from the internet, so all
Telegram communication is routed through the Render relay service:

  HA bot ──POST /api/notify──────────► relay ──► Telegram users (broadcast)
  HA bot ──GET  /api/commands─────────► relay     (clears & returns queue)
  HA bot ──POST /api/command-result──► relay ──► specific user chat
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Dict, List, Optional

logger = logging.getLogger("crypto_bot.telegram")


class TelegramNotifier:
    """Sends notifications and polls commands from the Render relay service."""

    def __init__(self, relay_url: str, api_key: str, timeout: int = 10):
        self._relay_url = relay_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify(self, html: str) -> None:
        """Broadcast an HTML-formatted message to all Telegram users."""
        if not self._relay_url or not html:
            return
        self._post("/api/notify", {"text": html})

    def poll_commands(self) -> List[Dict]:
        """
        Fetch (and clear) all pending commands from the relay.
        Returns a list of command dicts:
          { "id": str, "command": str, "args": str,
            "chat_id": int, "timestamp": str }
        """
        if not self._relay_url:
            return []
        result = self._get("/api/commands")
        if result and isinstance(result.get("commands"), list):
            return result["commands"]
        return []

    def send_result(self, chat_id: int, html: str) -> None:
        """Send a command result to a specific Telegram chat."""
        if not self._relay_url or not chat_id or not html:
            return
        self._post("/api/command-result", {"chat_id": chat_id, "text": html})

    # ------------------------------------------------------------------
    # Internal HTTP helpers (stdlib only – no extra dependencies)
    # ------------------------------------------------------------------

    def _post(self, path: str, body: dict) -> Optional[dict]:
        url = f"{self._relay_url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self._api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            logger.warning(f"Telegram relay POST {path} failed: {exc}")
            return None

    def _get(self, path: str) -> Optional[dict]:
        url = f"{self._relay_url}{path}"
        req = urllib.request.Request(
            url,
            headers={"X-API-Key": self._api_key},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            logger.warning(f"Telegram relay GET {path} failed: {exc}")
            return None
