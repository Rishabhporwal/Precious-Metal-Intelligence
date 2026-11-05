"""Daily brief (§15): THE CALL in your pocket — deterministic composition,
no LLM. One Telegram message each morning: price context, the standing
signal with its plan numbers, the four evidence verdicts, and event risk.

Everything comes from persisted data; if the signal is WAIT the brief says
so plainly — it never dresses a non-call up as a call.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.db import get_pool
from providers.telegram import send_message

IST = timezone(timedelta(hours=5, minutes=30))
BRIEF_HOUR_IST = 8


def compose_brief(symbol: str = "XAUUSD") -> str | None:
    symbol = symbol.upper()
    now = datetime.now(UTC)
    lines: list[str] = []
    with get_pool().connection() as conn:
        sig = conn.execute(
            """
            SELECT signal_type, created_at, price, score, plan, reconciliation, invalidation_level
            FROM trading_signals WHERE symbol = %s ORDER BY created_at DESC LIMIT 1
            """,
            (symbol,),
        ).fetchone()
        quote = conn.execute(
            """
            SELECT q.price FROM market_quotes q
            JOIN instruments i ON i.id = q.instrument_id
            WHERE i.symbol = %s ORDER BY q.market_ts DESC LIMIT 1
            """,
            (symbol,),
        ).fetchone()
        prev_close = conn.execute(
            """
            SELECT c.close, c.market_ts FROM market_candles c
            JOIN instruments i ON i.id = c.instrument_id
            WHERE i.symbol = %s AND c.interval = '1day' AND c.market_ts < %s
            ORDER BY c.market_ts DESC LIMIT 1
            """,
            (symbol, now.replace(hour=0, minute=0, second=0, microsecond=0)),
        ).fetchone()
        events = conn.execute(
            """
            SELECT release_name, event_date FROM economic_events
            WHERE event_date BETWEEN %s AND %s
            ORDER BY event_date LIMIT 3
            """,
            (now.date(), (now + timedelta(days=2)).date()),
        ).fetchall()

    if quote and prev_close:
        price = float(quote["price"])
        pc = float(prev_close["close"])
        chg = (price - pc) / pc * 100
        lines.append(f"Gold ${price:,.2f} ({chg:+.2f}% vs prior close)")

    if sig is None:
        lines.append("No signal generated yet — the engine is still warming up.")
        return "\n".join(lines) if lines else None

    st = sig["signal_type"].replace("_", " ")
    score = sig["score"]
    call: str
    if st in ("BUY", "STRONG BUY", "SELL", "STRONG SELL"):
        call = f"THE CALL: {st} (score {score})"
    elif st in ("EARLY BUY", "EARLY SELL"):
        call = f"THE CALL: {st} — early, smaller size (score {score})"
    else:
        call = f"Standing back: {st} (score {score})"
        if st == "WAIT":
            rec = sig.get("reconciliation") or {}
            fund = (rec.get("fundamental") or {})
            if "EVENT RISK" in str(fund.get("verdict", "")):
                call += " — high-impact event within 48h, platform is standing down"
    lines.append(call)

    plan = sig.get("plan") if isinstance(sig.get("plan"), dict) else {}
    pz = plan.get("entry_zone") or []
    if pz and plan.get("stop") is not None:
        entry_txt = f"${pz[0]:,.0f}–${pz[1]:,.0f}" if len(pz) == 2 else f"${pz[0]:,.0f}"
        lines.append(
            f"Plan: entry {entry_txt} · stop ${plan['stop']:,.0f}"
            + (f" · targets ${plan['t1']:,.0f} / ${plan['t2']:,.0f}" if plan.get("t1") else "")
        )
        if sig.get("invalidation_level") is not None:
            lines.append(f"Call is invalid below/above ${sig['invalidation_level']:,.0f}")

    rec = sig.get("reconciliation") or {}
    tiles = [
        ("Technical", rec.get("technical", {}).get("verdict")),
        ("Fundamental", rec.get("fundamental", {}).get("verdict")),
        ("Market reaction", rec.get("market_reaction", {}).get("verdict")),
        ("Quantitative", rec.get("quantitative", {}).get("verdict")),
    ]
    shown = [f"{k}: {v}" for k, v in tiles if v]
    if shown:
        lines.append("Evidence — " + " · ".join(shown))

    if events:
        ev = ", ".join(f"{e['release_name']} ({e['event_date']})" for e in events[:2])
        lines.append(f"This week: {ev}")

    age_h = (now - sig["created_at"]).total_seconds() / 3600
    lines.append(f"Signal set {age_h:.0f}h ago · SIMULATED ONLY, not financial advice")
    return "\n".join(lines)


def send_daily_brief(symbol: str = "XAUUSD") -> tuple[bool, str | None]:
    text = compose_brief(symbol)
    if text is None:
        return False, "nothing to send (no data)"
    return send_message(f"☀️ Gold Brief — {datetime.now(IST):%a %d %b}\n\n{text}")


def due_for_brief(last_sent_date) -> bool:
    now = datetime.now(IST)
    return now.hour >= BRIEF_HOUR_IST and (last_sent_date is None or last_sent_date != now.date())
