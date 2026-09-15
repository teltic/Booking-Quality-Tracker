"""Thin wrapper around PriceLabs' Customer API.

Base URL, auth (`X-API-Key` header), and every path in `ENDPOINTS` below
have been confirmed against a real account with a live API key (2026-09-14):
`listing_prices`, `neighborhood_data`, `overrides`, and `reservation_data`
all returned real data end-to-end. `listings` (used only if you call
`get_listings` directly -- the main workflow doesn't) is still unverified,
since nothing in the normal run exercises it; if it 404s, it's likely
`/v1/listings` needs the same `{resource}/{id}/...` nesting style overrides
turned out to need (`/listings/{id}/overrides`, not `/listing_data/...`).

If any endpoint ever starts 404/405ing (a PriceLabs API change, a plan/
permission difference, etc.), every call in this file goes through
`_request`, so the failure surfaces immediately with the failing URL and
response body rather than silently.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pricelabs.co/v1"

ENDPOINTS = {
    "listings": "/listings",
    "listing_prices": "/listing_prices",
    "neighborhood_data": "/neighborhood_data",
    "overrides": "/listings/{listing_id}/overrides",
    "reservation_data": "/reservation_data",
}


class PriceLabsAPIError(RuntimeError):
    def __init__(self, method: str, url: str, status_code: int, body: str):
        super().__init__(
            f"PriceLabs API call failed: {method} {url} -> HTTP {status_code}\n"
            f"Response body: {body[:2000]}\n"
            f"If this is a 404/405, the endpoint path in pricelabs_client.py's "
            f"ENDPOINTS dict is likely wrong -- check https://docs.pricelabs.co "
            f"and correct it there."
        )
        self.status_code = status_code
        self.body = body


class PriceLabsClient:
    def __init__(self, api_key: str, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update(
            {"X-API-Key": api_key, "Content-Type": "application/json"}
        )

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = BASE_URL + path
        resp = self.session.request(method, url, timeout=30, **kwargs)
        if not resp.ok:
            raise PriceLabsAPIError(method, url, resp.status_code, resp.text)
        return resp.json()

    def get_listings(self) -> list[dict]:
        data = self._request("GET", ENDPOINTS["listings"])
        return data.get("listings", data if isinstance(data, list) else [])

    def get_listing_prices(
        self, listing_id: str, pms: str, date_from: str, date_to: str
    ) -> list[dict]:
        """Per-date calendar: price, min_stay, booking_status, ADR, ADR_STLY, etc.

        Verified field names (live, 2026-09-12): date, price, user_price,
        uncustomized_price, min_stay, booking_status ("Booked"/""),
        booking_status_STLY, ADR, ADR_STLY, booked_date, booked_date_STLY,
        occupancy, check_in, check_out, demand_color, demand_desc.
        `date_from`/`date_to` must not be in the past for this endpoint.
        """
        body = {
            "listings": [{"id": listing_id, "pms": pms}],
            "date_from": date_from,
            "date_to": date_to,
        }
        data = self._request("POST", ENDPOINTS["listing_prices"], json=body)
        for entry in data:
            if entry.get("id") == listing_id:
                return entry.get("data", [])
        return []

    def get_neighborhood_data(self, listing_id: str, pms: str) -> dict:
        """Market comp-set data: percentiles, occupancy, comp-set metadata.

        Verified live shape (2026-09-12), nested under data["data"]:
          - "Neighborhood Data Source": str description of comp-set type/name
          - "Future Occ/New/Canc"."Category"[<comp name>]:
                "Listings Used": int
                "X_values": [dates...]
                "Y_values": [[...] per label in the sibling "Labels" list]
            Labels order: Occupancy, New Bookings, Canceled Bookings,
            Occupancy_LY, Occupancy_STLY, New_Bookings_STLY
          - "Future Percentile Prices"."Category"[<comp name>]:
                "X_values": [dates...], "Y_values": [[...] per label]
            Labels order: 25th Percentile, 50th Percentile, 75th Percentile,
            Median Booked Price, 90th Percentile, N_bookings
        A listing can have more than one Category key if its comp-set spans
        multiple market segments; this script uses the first one (matches
        the single-comp-set case seen live) -- revisit if a portfolio
        listing ever shows multiple categories.
        """
        data = self._request(
            "GET",
            ENDPOINTS["neighborhood_data"],
            params={"listing_id": listing_id, "pms": pms},
        )
        return data.get("data", data)

    def get_overrides(
        self,
        listing_id: str,
        pms: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """Active date overrides.

        Verified fields (live, 2026-09-12): date, price (string, may be
        absent), price_type ("percent"/"fixed"), min_stay, min_price,
        min_price_type, max_price, max_price_type, currency, reason,
        created_at, updated_at. A row with no `price` key is a
        restriction-only override (min_stay/min_price/max_price with no
        price push).
        """
        params = {"pms": pms}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        path = ENDPOINTS["overrides"].format(listing_id=listing_id)
        data = self._request("GET", path, params=params)
        return data.get("overrides", [])

    def get_reservations(
        self,
        pms: str,
        listing_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        booked_start_date: str | None = None,
        booked_end_date: str | None = None,
        page_size: int = 200,
    ) -> list[dict]:
        """Full reservation history, paginated.

        Verified fields (live, 2026-09-12): listing_id, listing_name,
        reservation_id, check_in, check_out, booking_status
        ("booked"/"cancelled"), booked_date, rental_revenue, total_cost,
        no_of_days, currency, cancelled_on, booking_channel,
        channelConfirmationCode, guest_count, ota_commission,
        cleaning_fees.

        NOTE: earlier attempts at pulling this data (via a different,
        older wrapped tool) silently returned only ~18 recent rows even
        with explicit date filters, instead of the full multi-year
        history a CSV export gave. When tested live against this
        account's reservation_data endpoint with an explicit multi-year
        start_date/end_date, it *did* return full history back to 2024
        with proper pagination (`next_page` + offset). Verify this holds
        for the directly-authenticated v1 endpoint too -- see
        bookings.py's `fetch_reservations_verified` for the sanity check
        and CSV fallback that guards against a regression of that bug.
        """
        results: list[dict] = []
        offset = 0
        while True:
            params: dict[str, Any] = {"pms": pms, "limit": page_size, "offset": offset}
            if listing_id:
                params["listing_id"] = listing_id
            if start_date and end_date:
                params["start_date"] = start_date
                params["end_date"] = end_date
            if booked_start_date:
                params["booked_start_date"] = booked_start_date
            if booked_end_date:
                params["booked_end_date"] = booked_end_date

            data = self._request("GET", ENDPOINTS["reservation_data"], params=params)
            page = data.get("data", [])
            results.extend(page)
            if not data.get("next_page") or not page:
                break
            offset += page_size
        return results
