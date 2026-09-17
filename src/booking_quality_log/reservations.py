"""Fetch confirmed reservations for a listing from PriceLabs.

Unlike the pricing tool's `bookings.py` (which needs deep multi-year
history and a CSV-truncation guard for LY/2LY aggregates), this tool only
needs a wide-enough window around "today" to compute median booking
windows, STLY same-date lookups, and gap-before/after context -- so it
fetches a bounded window rather than full history, and doesn't need a CSV
fallback.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .pricelabs_client import PriceLabsClient

CANCELLED_STATUSES = {"cancelled", "canceled"}

# How far back/forward of "today" to pull reservations. Back far enough to
# cover STLY (same calendar date last year) lookups for the earliest date
# this log shows, plus gap-before context for bookings right at that edge;
# forward far enough to catch essentially all real future bookings (Airbnb
# bookings this far out are rare, but PriceLabs itself doesn't cap this).
FETCH_BACK_DAYS = 400
FETCH_FORWARD_DAYS = 550


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    listing_name: str
    check_in: dt.date
    check_out: dt.date
    adr: float
    revenue: float
    booked_date: dt.date | None
    booking_channel: str
    booking_status: str
    confirmation_code: str = ""
    guest_count: int | None = None

    @property
    def is_confirmed(self) -> bool:
        return self.booking_status.strip().lower() not in CANCELLED_STATUSES

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    @property
    def display_id(self) -> str:
        """The channel confirmation code (e.g. an Airbnb code like
        "HMT5EBPQ54") when available -- this is what the original
        hand-built log used as its "Reservation ID" column, since it's
        human-recognizable, unlike PriceLabs' own internal reservation_id.
        """
        return self.confirmation_code or self.reservation_id


def _parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    return dt.date.fromisoformat(s[:10])


def _parse_guest_count(row: dict) -> int | None:
    raw = row.get("guest_count")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _from_api_rows(rows: list[dict]) -> list[Reservation]:
    out = []
    for row in rows:
        try:
            check_in = _parse_date(row["check_in"])
            check_out = _parse_date(row["check_out"])
            no_of_days = float(row.get("no_of_days") or 0)
            revenue = float(row.get("rental_revenue") or 0)
            adr = revenue / no_of_days if no_of_days > 0 else 0.0
            out.append(
                Reservation(
                    reservation_id=str(row.get("reservation_id", "")),
                    listing_name=row.get("listing_name", ""),
                    check_in=check_in,
                    check_out=check_out,
                    adr=adr,
                    revenue=revenue,
                    booked_date=_parse_date(row.get("booked_date")),
                    booking_channel=row.get("booking_channel", "") or "",
                    booking_status=row.get("booking_status", ""),
                    confirmation_code=str(row.get("channelConfirmationCode", "") or ""),
                    guest_count=_parse_guest_count(row),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return out


def fetch_reservations(
    client: PriceLabsClient,
    pms: str,
    listing_id: str,
    today: dt.date | None = None,
) -> list[Reservation]:
    """Fetch this listing's reservations (both confirmed and cancelled)
    across a window wide enough for gap/STLY/booking-window-median
    calculations. Callers filter by `.is_confirmed` as needed -- kept
    unfiltered here so a cancelled booking can still show up as a row
    (see compute.build_booking_rows) instead of silently vanishing.
    """
    today = today or dt.date.today()
    start = today - dt.timedelta(days=FETCH_BACK_DAYS)
    end = today + dt.timedelta(days=FETCH_FORWARD_DAYS)

    rows = client.get_reservations(
        pms=pms,
        listing_id=listing_id,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    reservations = _from_api_rows(rows)
    return [r for r in reservations if r.check_in and r.check_out]


def nightly_adr_series(reservations: list[Reservation]) -> dict[dt.date, float]:
    """Expand each reservation's blended ADR into one value per night stayed."""
    series: dict[dt.date, float] = {}
    for r in reservations:
        d = r.check_in
        while d < r.check_out:
            series[d] = r.adr
            d += dt.timedelta(days=1)
    return series
