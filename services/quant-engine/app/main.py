import redis.asyncio as aioredis
from fastapi import FastAPI
from pydantic import BaseModel

from .api import (
    analyst,
    backtests,
    dataquality_ep,
    macro,
    market_data,
    quant_stats,
    strategies,
    technical,
    trading,
    verdict,
)
from .config import get_settings

app = FastAPI(title="PMI Quant Engine", version="0.1.0")

settings = get_settings()

app.include_router(market_data.router)
app.include_router(technical.router)
app.include_router(strategies.router)
app.include_router(macro.router)
app.include_router(quant_stats.router)
app.include_router(analyst.router)
app.include_router(trading.router)
app.include_router(verdict.router)
app.include_router(backtests.router)
app.include_router(dataquality_ep.router)


class DependencyStatus(BaseModel):
    status: str  # "up" | "down" | "unconfigured"
    latency_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    dependencies: dict[str, DependencyStatus]


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness: process is running. Must not fail on dependency problems."""
    return HealthResponse(status="ok", service="pmi-quant", version=app.version or "0.0.0")


@app.get("/ready", response_model=ReadinessResponse)
async def ready() -> ReadinessResponse:
    """Readiness: critical dependencies reachable. 503 when any is down."""
    dependencies: dict[str, DependencyStatus] = {}

    if settings.database_url:
        import time

        start = time.perf_counter()
        try:
            import psycopg

            with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            dependencies["postgres"] = DependencyStatus(
                status="up", latency_ms=int((time.perf_counter() - start) * 1000)
            )
        except Exception as exc:  # noqa: BLE001 — health probe reports any failure
            dependencies["postgres"] = DependencyStatus(
                status="down", latency_ms=int((time.perf_counter() - start) * 1000), error=str(exc)
            )
    else:
        dependencies["postgres"] = DependencyStatus(status="unconfigured")

    if settings.redis_url:
        import time

        start = time.perf_counter()
        try:
            client = aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
            pong = await client.ping()
            await client.aclose()
            dependencies["redis"] = DependencyStatus(
                status="up" if pong else "down",
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            dependencies["redis"] = DependencyStatus(
                status="down", latency_ms=int((time.perf_counter() - start) * 1000), error=str(exc)
            )
    else:
        dependencies["redis"] = DependencyStatus(status="unconfigured")

    all_ready = all(d.status in ("up", "unconfigured") for d in dependencies.values())
    return ReadinessResponse(status="ready" if all_ready else "degraded", dependencies=dependencies)
