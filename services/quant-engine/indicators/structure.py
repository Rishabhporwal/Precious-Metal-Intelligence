"""Market structure detection — deterministic, confirmation-delayed, repaint-free.

Swing rule: bar i is a swing high (low) if its high (low) is the strict maximum
(minimum) of the k bars on each side (k = confirmation bars). A swing is only
"confirmed" k bars after it forms — detections reference the confirmation
index, never the future.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .oscillators import adx, ema

SWING_K = 2


@dataclass(frozen=True)
class Swing:
    index: int  # candle index of the pivot
    confirmed_index: int  # index at which the swing became known (index + k)
    price: float
    kind: str  # "high" | "low"


@dataclass(frozen=True)
class StructureEvent:
    kind: str  # "bos_bullish" | "bos_bearish" | "choch_bullish" | "choch_bearish"
    index: int  # candle index of the closing bar that confirmed the event
    level: float  # the broken swing level
    swing_index: int
    detail: str = ""


@dataclass
class StructureReport:
    swings: list[Swing] = field(default_factory=list)
    events: list[StructureEvent] = field(default_factory=list)
    supports: list[dict] = field(default_factory=list)
    resistances: list[dict] = field(default_factory=list)
    labels: list[tuple[int, str]] = field(default_factory=list)  # (swing index, "HH"/"HL"/...)
    trend: str = "unknown"  # "up" | "down" | "sideways"
    pdh: float | None = None
    pdl: float | None = None
    pwh: float | None = None
    pwl: float | None = None
    sessions: dict[str, dict] = field(default_factory=dict)


def detect_swings(
    highs: list[float], lows: list[float], k: int = SWING_K
) -> list[Swing]:
    out: list[Swing] = []
    n = len(highs)
    for i in range(k, n - k):
        window_h = highs[i - k : i + k + 1]
        window_l = lows[i - k : i + k + 1]
        if highs[i] == max(window_h) and window_h.count(highs[i]) == 1:
            out.append(Swing(index=i, confirmed_index=i + k, price=highs[i], kind="high"))
        if lows[i] == min(window_l) and window_l.count(lows[i]) == 1:
            out.append(Swing(index=i, confirmed_index=i + k, price=lows[i], kind="low"))
    out.sort(key=lambda s: (s.index, s.kind))
    return out


def label_swings(swings: list[Swing]) -> list[tuple[int, str]]:
    """Classify consecutive same-kind swings as HH/LH (highs) and HL/LL (lows)."""
    labels: list[tuple[int, str]] = []
    prev_high: Swing | None = None
    prev_low: Swing | None = None
    for s in swings:
        if s.kind == "high":
            if prev_high is not None:
                labels.append((s.index, "HH" if s.price > prev_high.price else "LH"))
            prev_high = s
        else:
            if prev_low is not None:
                labels.append((s.index, "HL" if s.price > prev_low.price else "LL"))
            prev_low = s
    return labels


def detect_structure_events(
    closes: list[float], swings: list[Swing]
) -> list[StructureEvent]:
    """BOS/CHoCH using confirmed swings and closed candles only.

    Walk candles in order; maintain the most recent confirmed swing high/low.
    A close above the last swing high breaks structure to the upside; whether
    that is BOS or CHoCH depends on the direction of the previous break.
    """
    events: list[StructureEvent] = []
    n = len(closes)
    swing_iter = iter(swings)
    pending = next(swing_iter, None)
    active_high: Swing | None = None
    active_low: Swing | None = None
    last_direction: str | None = None  # "up" | "down" from the most recent break

    for i in range(n):
        # activate swings whose confirmation index has arrived (i >= confirmed_index)
        while pending is not None and pending.confirmed_index <= i:
            if pending.kind == "high":
                if active_high is None or pending.price > active_high.price or pending.index > active_high.index:
                    if active_high is None or pending.index > active_high.index:
                        active_high = pending
            else:
                if active_low is None or pending.index > active_low.index:
                    active_low = pending
            pending = next(swing_iter, None)

        c = closes[i]
        if active_high is not None and c > active_high.price:
            kind = (
                "choch_bullish"
                if last_direction == "down"
                or (last_direction is None and _prev_trend_down(events))
                else "bos_bullish"
            )
            if not events or events[-1].kind != kind or events[-1].level != active_high.price:
                events.append(
                    StructureEvent(
                        kind=kind, index=i, level=active_high.price,
                        swing_index=active_high.index,
                        detail=f"close {c:.4f} above swing high {active_high.price:.4f}",
                    )
                )
            last_direction = "up"
            active_high = None  # level consumed; next swing high takes over
        elif active_low is not None and c < active_low.price:
            kind = (
                "choch_bearish"
                if last_direction == "up"
                or (last_direction is None and _prev_trend_up(events))
                else "bos_bearish"
            )
            if not events or events[-1].kind != kind or events[-1].level != active_low.price:
                events.append(
                    StructureEvent(
                        kind=kind, index=i, level=active_low.price,
                        swing_index=active_low.index,
                        detail=f"close {c:.4f} below swing low {active_low.price:.4f}",
                    )
                )
            last_direction = "down"
            active_low = None
    return events


def _prev_trend_down(events: list[StructureEvent]) -> bool:
    return bool(events) and events[-1].kind in ("bos_bearish", "choch_bearish")


def _prev_trend_up(events: list[StructureEvent]) -> bool:
    return bool(events) and events[-1].kind in ("bos_bullish", "choch_bullish")


def support_resistance(
    swings: list[Swing],
    last_close: float,
    tolerance_pct: float = 0.003,
    max_levels: int = 5,
) -> tuple[list[dict], list[dict]]:
    """Cluster swing prices into levels; count touches. Nearest levels first."""
    levels: list[dict] = []
    tol = last_close * tolerance_pct
    for s in sorted(swings, key=lambda s: s.price):
        if levels and abs(s.price - levels[-1]["price"]) <= tol:
            levels[-1]["touches"] += 1
            levels[-1]["price"] = (levels[-1]["price"] * (levels[-1]["touches"] - 1) + s.price) / levels[-1]["touches"]
            levels[-1]["last_index"] = max(levels[-1]["last_index"], s.index)
        else:
            levels.append({"price": s.price, "touches": 1, "last_index": s.index})
    supports = sorted(
        (l for l in levels if l["price"] < last_close),
        key=lambda l: l["price"], reverse=True,
    )[:max_levels]
    resistances = sorted(
        (l for l in levels if l["price"] >= last_close),
        key=lambda l: l["price"],
    )[:max_levels]
    return supports, resistances


def prev_day_high_low(daily: list[dict]) -> tuple[float | None, float | None]:
    """Yesterday's high/low from the last COMPLETED daily candle (provisional excluded)."""
    completed = [d for d in daily if d.get("status", "final") == "final"]
    if len(completed) < 1:
        return None, None
    yesterday = completed[-1]
    return float(yesterday["high"]), float(yesterday["low"])


def prev_week_high_low(daily: list[dict]) -> tuple[float | None, float | None]:
    """Last completed ISO week's high/low from daily candles."""
    completed = [d for d in daily if d.get("status", "final") == "final"]
    if not completed:
        return None, None
    by_week: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for d in completed:
        ts = d["market_ts"]
        dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
        iso = dt.isocalendar()
        by_week[(iso[0], iso[1])].append(d)
    weeks = sorted(by_week)
    if len(weeks) < 1:
        return None, None
    last_week = by_week[weeks[-1]]
    # if the last week is the current (still-running) week and has <5 candles,
    # it is provisional — use the previous completed week instead.
    if len(last_week) < 5 and len(weeks) >= 2:
        last_week = by_week[weeks[-2]]
    return max(float(d["high"]) for d in last_week), min(float(d["low"]) for d in last_week)


# UTC session windows (gold trades ~23h/day; sessions defined in UTC for determinism)
SESSION_WINDOWS = {
    "asia": (0, 8),
    "london": (7, 16),
    "newyork": (12, 21),
}


def session_ranges(hourly: list[dict], ref_date: datetime | None = None) -> dict[str, dict]:
    """High/low per session window for the most recent completed UTC day."""
    if not hourly:
        return {}
    times = [
        h["market_ts"] if isinstance(h["market_ts"], datetime) else datetime.fromisoformat(str(h["market_ts"]))
        for h in hourly
    ]
    last_day = (ref_date or max(times)).astimezone(UTC).date() - timedelta(days=1)
    day_candles = [
        (t, h) for t, h in zip(times, hourly, strict=True)
        if t.astimezone(UTC).date() == last_day
    ]
    out: dict[str, dict] = {}
    for name, (start_h, end_h) in SESSION_WINDOWS.items():
        window = [
            h for t, h in day_candles
            if start_h <= t.astimezone(UTC).hour < end_h
        ]
        if window:
            out[name] = {
                "date": last_day.isoformat(),
                "high": max(float(h["high"]) for h in window),
                "low": min(float(h["low"]) for h in window),
            }
    return out


def mtf_trend(
    closes_by_interval: dict[str, list[float]],
    highs_by_interval: dict[str, list[float]],
    lows_by_interval: dict[str, list[float]],
) -> list[dict]:
    """Trend per interval from EMA alignment (20/50/200) + ADX strength."""
    out = []
    for interval, closes in closes_by_interval.items():
        if len(closes) < 50:
            out.append({"interval": interval, "trend": "unknown", "strength": None,
                        "detail": "insufficient data"})
            continue
        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        e200 = ema(closes, 200) if len(closes) >= 200 else None
        a, _, _ = adx(highs_by_interval[interval], lows_by_interval[interval], closes)
        last = closes[-1]
        v20 = e20[-1]
        v50 = e50[-1]
        v200 = e200[-1] if e200 else None
        score = 0
        if v20 is not None:
            score += 1 if last > v20 else -1
        if v50 is not None:
            score += 1 if last > v50 else -1
        if v20 is not None and v50 is not None:
            score += 1 if v20 > v50 else -1
        if v200 is not None:
            score += 1 if last > v200 else -1
            score += 1 if (v50 is not None and v50 > v200) else -1
        trend = "up" if score >= 3 else "down" if score <= -3 else "sideways"
        adx_last = a[-1] if a else None
        strength = None
        if adx_last is not None:
            strength = "strong" if adx_last >= 25 else "moderate" if adx_last >= 20 else "weak"
        out.append({
            "interval": interval,
            "trend": trend,
            "strength": strength,
            "adx": round(adx_last, 1) if adx_last is not None else None,
            "detail": f"alignment score {score}",
        })
    return out


def full_structure_report(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    daily: list[dict],
    hourly: list[dict],
    ref_date: datetime | None = None,
) -> StructureReport:
    swings = detect_swings(highs, lows)
    events = detect_structure_events(closes, swings)
    labels = label_swings(swings)
    supports, resistances = support_resistance(swings, closes[-1] if closes else 0.0)
    pdh, pdl = prev_day_high_low(daily)
    pwh, pwl = prev_week_high_low(daily)
    sessions = session_ranges(hourly, ref_date=ref_date)
    # trend from recent labeled swings (last 6 labels)
    recent = labels[-6:] if labels else []
    ups = sum(1 for _, l in recent if l in ("HH", "HL"))
    downs = sum(1 for _, l in recent if l in ("LH", "LL"))
    trend = "up" if ups >= 4 else "down" if downs >= 4 else "sideways"
    return StructureReport(
        swings=swings[-50:],
        events=events[-20:],
        supports=supports,
        resistances=resistances,
        labels=recent,
        trend=trend,
        pdh=pdh, pdl=pdl, pwh=pwh, pwl=pwl,
        sessions=sessions,
    )
