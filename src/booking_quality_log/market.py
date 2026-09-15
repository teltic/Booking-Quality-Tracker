"""Parse PriceLabs' neighborhood/market-data response into a per-date table.

See PriceLabsClient.get_neighborhood_data for the verified raw shape. This
module flattens it into `{date: MarketDay}` plus the comp-set summary used
by the Compset Overview tab.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class MarketDay:
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None
    occupancy_stly: float | None
    occupancy: float | None = None


@dataclass(frozen=True)
class CompsetInfo:
    source_label: str
    category_name: str
    listings_used: int | None
    notes: str = ""


OCC_LABELS = [
    "Occupancy",
    "New Bookings",
    "Canceled Bookings",
    "Occupancy_LY",
    "Occupancy_STLY",
    "New_Bookings_STLY",
]
PRICE_LABELS = [
    "25th Percentile",
    "50th Percentile",
    "75th Percentile",
    "Median Booked Price",
    "90th Percentile",
    "N_bookings",
]


def _select_primary_category(section: dict) -> tuple[str, dict] | tuple[None, None]:
    """Pick the category with the most listings.

    A comp-set segmented by bedroom count (PriceLabs' "Nearby Listings"
    style, as opposed to a single curated amenity-based comp) returns one
    sub-category per bedroom bucket rather than one blended group. Taking
    "whichever key comes first" can land on a bucket with as few as 1
    listing, which makes every percentile column identical (25th = 50th =
    75th = 90th, since there's only one data point) -- picking the bucket
    with the most listings gives the most statistically meaningful spread.
    """
    categories = section.get("Category", {})
    if not categories:
        return None, None
    name = max(categories, key=lambda k: categories[k].get("Listings Used", 0) or 0)
    return name, categories[name]


def parse_market_data(raw: dict) -> tuple[dict[dt.date, MarketDay], CompsetInfo]:
    occ_section = raw.get("Future Occ/New/Canc", {})
    price_section = raw.get("Future Percentile Prices", {})

    occ_cat_name, occ_cat = _select_primary_category(occ_section)
    price_cat_name, price_cat = _select_primary_category(price_section)

    occ_by_date: dict[str, float] = {}
    current_occ_by_date: dict[str, float] = {}
    if occ_cat:
        x_values = occ_cat.get("X_values", [])
        y_values = occ_cat.get("Y_values", [])
        stly_idx = OCC_LABELS.index("Occupancy_STLY")
        if len(y_values) > stly_idx:
            occ_by_date = dict(zip(x_values, y_values[stly_idx]))
        current_idx = OCC_LABELS.index("Occupancy")
        if len(y_values) > current_idx:
            current_occ_by_date = dict(zip(x_values, y_values[current_idx]))

    price_by_date: dict[str, tuple] = {}
    if price_cat:
        x_values = price_cat.get("X_values", [])
        y_values = price_cat.get("Y_values", [])
        if len(y_values) >= 4:
            p25, p50, p75, _median, p90 = y_values[0], y_values[1], y_values[2], y_values[3], y_values[4]
            for i, date_str in enumerate(x_values):
                price_by_date[date_str] = tuple(round(v, 2) if v is not None else None for v in (p25[i], p50[i], p75[i], p90[i]))

    all_dates = set(occ_by_date) | set(price_by_date) | set(current_occ_by_date)
    result: dict[dt.date, MarketDay] = {}
    for date_str in all_dates:
        p25, p50, p75, p90 = price_by_date.get(date_str, (None, None, None, None))
        result[dt.date.fromisoformat(date_str)] = MarketDay(
            p25=p25,
            p50=p50,
            p75=p75,
            p90=p90,
            occupancy_stly=occ_by_date.get(date_str),
            occupancy=current_occ_by_date.get(date_str),
        )

    all_categories = list(price_section.get("Category", {}).keys()) or list(
        occ_section.get("Category", {}).keys()
    )
    primary_name = price_cat_name or occ_cat_name or ""
    notes = ""
    if len(all_categories) > 1:
        total_across_segments = sum(
            (price_section.get("Category", {}).get(name) or occ_section.get("Category", {}).get(name) or {}).get(
                "Listings Used", 0
            )
            or 0
            for name in all_categories
        )
        category_name = f"{primary_name} (of {len(all_categories)} segments: {', '.join(sorted(all_categories))})"
        notes = (
            f"Comp-set is split into {len(all_categories)} bedroom-count segments; "
            f"percentiles above use the largest one ('{primary_name}'). Combined "
            f"segments cover {total_across_segments} listings total (may double-count "
            f"any listing appearing in more than one segment)."
        )
        listings_used = total_across_segments
    else:
        category_name = primary_name
        listings_used = (price_cat or occ_cat or {}).get("Listings Used")

    compset = CompsetInfo(
        source_label=raw.get("Neighborhood Data Source", ""),
        category_name=category_name,
        listings_used=listings_used,
        notes=notes,
    )
    return result, compset


def market_percentile_bucket(price: float | None, day: MarketDay | None) -> str:
    if price is None or day is None or day.p25 is None:
        return ""
    if price < day.p25:
        return "<25th"
    if price < day.p50:
        return "25th-50th"
    if price < day.p75:
        return "50th-75th"
    if price < day.p90:
        return "75th-90th"
    return ">90th"
