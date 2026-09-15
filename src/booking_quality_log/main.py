"""CLI entrypoint: pull live PriceLabs data for every configured listing
and, if at least one brand-new confirmed booking has shown up since the
last run, write today's "Booking Quality Log" workbook.

Usage:
    python -m booking_quality_log.main [--output-dir DIR] [--force]

Meant to run once a day (see run_daily.bat / setup_daily_task.bat).
Safe to rerun same-day: it reads the most recent prior dated file in
`--output-dir`, compares its Reservation IDs against today's confirmed
bookings, and only writes a new file when there's at least one Reservation
ID today that wasn't already known (whether previously shown as confirmed
or cancelled). Five manual note columns (Comp Check, Pacing Push %, LOS
Discount, Final PL Check, Notes / Verdict) are carried forward from that
same prior file, matched by Reservation ID, whenever a file is written --
including for a booking that's since been cancelled, which stays visible
(marked Cancelled) rather than dropping out of the log.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from . import config as cfg
from .market import parse_market_data
from .pricelabs_client import PriceLabsAPIError, PriceLabsClient

from .compute import START_DATE, build_booking_rows
from .dated_output import dated_filename, find_most_recent_prior_file
from .reservations import fetch_reservations
from .workbook_build import build_booking_quality_sheet, build_read_me_sheet, new_workbook
from .workbook_state import load_prior_reservation_state

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = cfg.REPO_ROOT / "output"


def run(
    output_dir: Path,
    listings_config: Path | None = None,
    today: dt.date | None = None,
    force: bool = False,
) -> bool:
    """Returns True if a file was written, False if today was skipped."""
    today = today or dt.date.today()
    listings = cfg.load_listings(listings_config)
    api_key = cfg.get_api_key()
    client = PriceLabsClient(api_key)

    output_dir.mkdir(parents=True, exist_ok=True)
    prior_path = find_most_recent_prior_file(output_dir, today)
    prior_state = load_prior_reservation_state(prior_path) if prior_path else {}
    if prior_path is None:
        logger.info("No prior Booking Quality Log found in %s -- this is the first run.", output_dir)
    else:
        logger.info("Carrying manual notes forward from %s", prior_path)

    all_rows = []
    for listing in listings:
        logger.info("Processing %s (%s / %s)", listing.name, listing.pms, listing.listing_id)
        reservations = fetch_reservations(client, listing.pms, listing.listing_id, today)
        raw_market = client.get_neighborhood_data(listing.listing_id, listing.pms)
        market, _compset = parse_market_data(raw_market)
        all_rows.extend(build_booking_rows(listing.name, reservations, market))

    # Newest-booked first (column "Booked" = the date the reservation was
    # made, not check-in) -- rows with no booked_date sort to the bottom.
    all_rows.sort(key=lambda r: (r.booked_date or dt.date.min, r.check_in), reverse=True)

    # Only a brand-new *confirmed* booking counts as "new" for the daily
    # skip check -- a booking that was already known (whether it showed as
    # Confirmed or Cancelled in the prior file) isn't new, and a
    # cancellation by itself never triggers a write.
    today_confirmed_ids = {row.reservation_id for row in all_rows if row.status == "Confirmed"}
    new_ids = today_confirmed_ids - set(prior_state.keys())

    if prior_path is not None and not new_ids and not force:
        logger.info(
            "No new confirmed bookings since %s (%d confirmed bookings in view, none new) "
            "-- skipping today.",
            prior_path.name,
            len(today_confirmed_ids),
        )
        return False

    if new_ids:
        logger.info("%d new confirmed booking(s) found: %s", len(new_ids), sorted(new_ids))
    elif force:
        logger.info("--force given: writing today's file even though nothing new was found.")

    wb = new_workbook()
    build_read_me_sheet(wb)
    build_booking_quality_sheet(wb, all_rows, START_DATE, manual_notes=prior_state)

    write_path = output_dir / dated_filename(today)
    try:
        wb.save(write_path)
    except PermissionError as exc:
        raise SystemExit(
            f"Could not write {write_path} -- it's most likely open in Excel "
            f"(or another program) right now, which locks the file. Close it "
            f"and run this again."
        ) from exc
    logger.info("Saved %s", write_path)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder to write today's dated workbook into (and read the most "
        "recent prior one from, to check for new bookings and carry manual "
        "notes forward).",
    )
    parser.add_argument("--listings-config", type=Path, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Write today's file even if no new confirmed booking was found.",
    )
    args = parser.parse_args(argv)

    try:
        run(args.output_dir, args.listings_config, force=args.force)
    except PriceLabsAPIError as exc:
        logger.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
