"""Data-quality endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.dataquality import quality_report

router = APIRouter(prefix="/v1/data", tags=["data-quality"])


@router.get("/quality")
def quality(symbol: str = "XAUUSD") -> dict:
    return quality_report(symbol)
