"""Extracts just the dated `reason` text from PriceLabs' date-overrides
response -- the free-text note you already type by hand when pushing a
pacing/LY-driven override (e.g. "9/12 - Pacing behind by -15.79%").

This is intentionally a much thinner parse than the sibling pricing
tool's own overrides.py (which also tracks price/min-stay/sign for
building an Overrides tab) -- here it's only ever used as bonus context
text on a booking row, never a computed metric.
"""

from __future__ import annotations

import datetime as dt


def parse_override_reasons(raw_rows: list[dict]) -> dict[dt.date, str]:
    result: dict[dt.date, str] = {}
    for row in raw_rows:
        reason = (row.get("reason") or "").strip()
        if not reason:
            continue
        try:
            d = dt.date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue
        result[d] = reason
    return result
