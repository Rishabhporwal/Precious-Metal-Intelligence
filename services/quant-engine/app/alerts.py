"""Alert engine: rules, evaluation with cooldown/dedupe, delivery via Telegram.

A continuously-true condition must not repeat: every fired alert is recorded in
alert_events and the rule's cooldown window suppresses re-firing.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db import get_pool
from providers.telegram import send_message

logger = logging.getLogger("alerts")


def list_rules() -> list[dict]:
    with get_pool().connection() as conn:
        cur = conn.execute("SELECT * FROM alert_rules ORDER BY id")
        return cur.fetchall()


def create_rule(kind: str, symbol: str, params: dict, severity: str = "info",
                cooldown_seconds: int = 3600) -> dict:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO alert_rules (kind, symbol, params, severity, cooldown_seconds)
            VALUES (%s, %s, %s, %s, %s) RETURNING *
            """,
            (kind, symbol.upper(), __import__("json").dumps(params), severity, cooldown_seconds),
        )
        return cur.fetchone()


def delete_rule(rule_id: int) -> bool:
    with get_pool().connection() as conn:
        cur = conn.execute("DELETE FROM alert_rules WHERE id = %s RETURNING id", (rule_id,))
        return cur.fetchone() is not None


def recent_events(limit: int = 30) -> list[dict]:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT e.id, e.message, e.severity, e.delivered_telegram, e.delivery_error,
                   e.fired_at, r.kind, r.symbol
            FROM alert_events e JOIN alert_rules r ON r.id = e.rule_id
            ORDER BY e.fired_at DESC LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def _last_fired(conn, rule_id: int) -> datetime | None:
    cur = conn.execute(
        "SELECT MAX(fired_at) AS last FROM alert_events WHERE rule_id = %s", (rule_id,)
    )
    row = cur.fetchone()
    return row["last"] if row else None


def fire(rule: dict, message: str) -> bool:
    """Fire an alert (respecting cooldown) and deliver via Telegram. Returns delivered."""
    now = datetime.now(UTC)
    with get_pool().connection() as conn:
        last = _last_fired(conn, rule["id"])
        if last is not None:
            elapsed = (now - last).total_seconds()
            if elapsed < rule["cooldown_seconds"]:
                logger.debug("rule %d in cooldown (%.0fs < %ss)", rule["id"], elapsed, rule["cooldown_seconds"])
                return False
        delivered, error = send_message(message)
        conn.execute(
            """
            INSERT INTO alert_events (rule_id, message, severity, delivered_telegram, delivery_error)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (rule["id"], message, rule["severity"], delivered, error),
        )
    if not delivered:
        logger.info("alert (telegram unconfigured or failed): %s", message)
    return True


def evaluate_price_rules() -> int:
    """Evaluate price_above / price_below rules against the latest stored quotes."""
    fired = 0
    rules = [r for r in list_rules() if r["enabled"] and r["kind"] in ("price_above", "price_below")]
    with get_pool().connection() as conn:
        for rule in rules:
            inst = conn.execute(
                "SELECT id FROM instruments WHERE symbol = %s", (rule["symbol"],)
            ).fetchone()
            if inst is None:
                continue
            q = conn.execute(
                "SELECT price FROM market_quotes WHERE instrument_id = %s ORDER BY market_ts DESC LIMIT 1",
                (inst["id"],),
            ).fetchone()
            if q is None or q["price"] is None:
                continue
            price = float(q["price"])
            level = float((rule["params"] or {}).get("level", 0))
            label = (rule["params"] or {}).get("label", str(level))
            hit = (rule["kind"] == "price_above" and price >= level) or (
                rule["kind"] == "price_below" and price <= level
            )
            if hit:
                if fire(rule, f"XAUUSD {'≥' if rule['kind'] == 'price_above' else '≤'} {label}: now {price:.2f}"):
                    fired += 1
    return fired


def evaluate_new_detections() -> int:
    """Fire setup/sweep alerts for detections persisted after the last alert check."""
    fired = 0
    with get_pool().connection() as conn:
        rules = [
            r for r in list_rules()
            if r["enabled"] and r["kind"] in ("sweep", "fvg", "bos_choch", "setup_new")
        ]
        for rule in rules:
            since = _last_fired(conn, rule["id"]) or datetime(2000, 1, 1, tzinfo=UTC)
            kind_filter = {
                "sweep": "smc_liquidity_sweep",
                "fvg": "smc_fvg",
                "bos_choch": "ict_mss",
                "setup_new": "composite_sweep_mss_fvg_ob",
            }[rule["kind"]]
            cur = conn.execute(
                """
                SELECT d.strategy_id, d.direction, d.anchor_time, i.symbol
                FROM strategy_detections d
                JOIN instruments i ON i.id = d.instrument_id
                WHERE i.symbol = %s AND d.strategy_id = %s AND d.detected_at > %s
                ORDER BY d.detected_at DESC LIMIT 3
                """,
                (rule["symbol"], kind_filter, since),
            )
            for row in cur.fetchall():
                msg = (
                    f"{row['symbol']} {rule['kind'].upper()} {row['direction']} "
                    f"@ {row['anchor_time'].isoformat()[:16]}Z"
                )
                if fire(rule, msg):
                    fired += 1
    return fired


def evaluate_all() -> dict:
    return {
        "price_alerts_fired": evaluate_price_rules(),
        "detection_alerts_fired": evaluate_new_detections(),
    }
