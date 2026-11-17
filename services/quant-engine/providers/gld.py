"""GLD ETF daily holdings — the physical-demand proxy (SPDR official archive).

No API key needed. The archive is an XLSX refreshed after each US close; we
parse the last rows and store them so the verdict engine can weigh ETF
inflows/outflows as the physical-demand driver.
"""

from __future__ import annotations

import io
import logging
from datetime import date

import httpx

logger = logging.getLogger("gld")

ARCHIVE_URL = "https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en"

# column titles inside the "US GLD Historical Archive" sheet
COL_DATE = "Date"
COL_TONNES = "Tonnes of Gold"


def fetch_gld_holdings(max_rows: int = 15) -> list[dict]:
    """Return the newest rows: [{date: date, tonnes: float, closing_price: float}]."""
    import openpyxl

    resp = httpx.get(ARCHIVE_URL, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    wb = openpyxl.load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True)
    ws = wb["US GLD Historical Archive"]
    rows = ws.iter_rows(values_only=True)
    header = None
    idx = {}
    all_rows: list[dict] = []
    for row in rows:
        vals = [str(v).strip() if v is not None else "" for v in row]
        if header is None:
            if vals and vals[0] == COL_DATE:
                header = vals
                idx = {name: i for i, name in enumerate(header) if name}
            continue
        d_raw = vals[idx[COL_DATE]] if COL_DATE in idx else ""
        t_raw = vals[idx[COL_TONNES]] if COL_TONNES in idx else ""
        if not d_raw or not t_raw or d_raw.lower().endswith("holiday"):
            continue
        try:
            d = date.fromisoformat(d_raw.replace("-", "-")) if "-" in d_raw and len(d_raw) == 10 else None
            if d is None:
                # format "18-Nov-2004"
                from datetime import datetime

                d = datetime.strptime(d_raw, "%d-%b-%Y").date()
            tonnes = float(t_raw)
        except (ValueError, TypeError):
            continue
        price_raw = vals[idx["Closing Price"]] if "Closing Price" in idx else None
        try:
            price = float(price_raw) if price_raw else None
        except (ValueError, TypeError):
            price = None
        all_rows.append({"date": d, "tonnes": tonnes, "closing_price": price})
    # the archive is oldest-first — keep the newest rows, ascending
    # the archive is oldest-first — the NEWEST rows are at the end;
    # keep the last N and return them ascending by date
    return list(reversed(all_rows[-max_rows:]))