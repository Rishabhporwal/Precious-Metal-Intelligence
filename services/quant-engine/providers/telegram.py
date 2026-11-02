"""Telegram notification adapter. Unconfigured → honest no-op with delivery error."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("telegram")


def telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def send_message(text: str) -> tuple[bool, str | None]:
    """Returns (delivered, error). Never raises."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured"
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            return True, None
        return False, f"telegram HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram send failed: %s", exc)
        return False, str(exc)
