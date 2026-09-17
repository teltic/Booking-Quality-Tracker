import datetime as dt
from pathlib import Path

import openpyxl

from booking_quality_log.compute import BookingRow
from booking_quality_log.workbook_build import (
    MANUAL_COLS_COUNT,
    MANUAL_COLS_START,
    MANUAL_COLUMNS,
    build_booking_quality_sheet,
    new_workbook,
)
from booking_quality_log.workbook_state import load_prior_reservation_state


def _row(res_id):
    return BookingRow(
        property_name="Test Property",
        check_in=dt.date(2026, 9, 5),
        check_out=dt.date(2026, 9, 7),
        nights=2,
        guest_count=4,
        stay_pattern="Weekend-anchored",
        one_night_stay=False,
        booked_date=dt.date(2026, 8, 20),
        booking_window_days=16,
        bw_vs_median="Typical",
        my_adr=400.0,
        my_revenue=800.0,
        source="airbnb",
        target_adr_p75=380.0,
        vs_target_dollar=20.0,
        vs_target_pct=0.0526,
        my_season_adr="not enough data",
        vs_my_season_pct="n/a",
        market_p25=250.0,
        market_p90=420.0,
        stly_adr="no data",
        ly_occ="no data",
        demand_tier="High",
        gap_before_days="first known booking in window",
        gap_before_signal=None,
        gap_after_days=1,
        gap_after_signal="Upsell candidate (rarely fills alone)",
        status="Confirmed",
        reservation_id=res_id,
        override_notes="",
    )


# First and last manual columns (Comp Check / Lesson Learned) -- offsets
# within the manual block, used below instead of hardcoding column numbers.
COMP_CHECK_OFFSET = MANUAL_COLUMNS.index("Comp Check (Airbnb)")
LESSON_LEARNED_OFFSET = MANUAL_COLUMNS.index("Lesson Learned")


def test_missing_file_returns_empty_dict(tmp_path):
    assert load_prior_reservation_state(tmp_path / "nope.xlsx") == {}


def test_reads_reservation_ids_and_manual_columns(tmp_path):
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111"), _row("BBB222")], dt.date(2026, 9, 1))
    ws = wb["Booking Quality Log"]
    ws.cell(row=5, column=MANUAL_COLS_START + COMP_CHECK_OFFSET, value="checked on airbnb")
    ws.cell(row=6, column=MANUAL_COLS_START + LESSON_LEARNED_OFFSET, value="looks great")
    path = tmp_path / "prior.xlsx"
    wb.save(path)

    state = load_prior_reservation_state(path)
    assert set(state.keys()) == {"AAA111", "BBB222"}
    assert state["AAA111"][COMP_CHECK_OFFSET] == "checked on airbnb"
    assert state["BBB222"][LESSON_LEARNED_OFFSET] == "looks great"


def test_row_with_all_blank_manual_columns_still_counted_for_skip_check(tmp_path):
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1))
    path = tmp_path / "prior.xlsx"
    wb.save(path)

    state = load_prior_reservation_state(path)
    assert "AAA111" in state
    assert state["AAA111"] == (None,) * MANUAL_COLS_COUNT


def test_reads_an_older_layout_with_fewer_and_differently_named_manual_columns(tmp_path):
    # Simulates a file written by an older version of this tool, before
    # today's expanded manual-review block: no Status column, Reservation
    # ID at Z (26), only 5 manual columns, and "Notes / Verdict" (since
    # renamed to "Lesson Learned") plus a manual "LY Weekday Occ." column
    # that's since become the computed "LY occ." column. Matching every
    # column by header text -- not position -- is what lets a genuinely
    # unrenamed field like "Comp Check (Airbnb)" carry forward correctly
    # regardless of where either file put it, while a column that got
    # renamed or repurposed (not the same header text anymore) is
    # correctly left behind rather than misread into the wrong slot --
    # that's the tradeoff of matching by exact header text: a pure rename
    # needs the file regenerated once under the new name before its notes
    # carry forward again.
    wb = openpyxl.Workbook()
    del wb["Sheet"]
    ws = wb.create_sheet("Booking Quality Log")
    headers = [
        "Property", "Check-in", "In Day", "Check-out", "Out Day", "Nights",
        "Stay Pattern", "1-Night Stay", "Booked", "Booking Window (d)",
        "BW vs Median", "My ADR", "My Revenue", "Source", "Target ADR (P75)",
        "vs Target ($)", "vs Target (%)", "Market P25", "Market P90",
        "STLY ADR", "Demand Tier", "Gap Before (d)", "Gap Before Signal",
        "Gap After (d)", "Gap After Signal", "Reservation ID",
        "Comp Check (Airbnb)", "LY Weekday Occ.", "Pacing Push %",
        "LOS Discount", "Final PL Check", "Notes / Verdict",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=4, column=c, value=h)
    ws.cell(row=5, column=26, value="OLDID123")  # Z: Reservation ID (old position)
    ws.cell(row=5, column=27, value="checked, looked fine")  # old AA: Comp Check
    ws.cell(row=5, column=28, value="65% last year")  # old AB: LY Weekday Occ. (obsolete manual text)
    ws.cell(row=5, column=32, value="great find")  # old AF: Notes / Verdict (since renamed)
    path = tmp_path / "old_layout.xlsx"
    wb.save(path)

    state = load_prior_reservation_state(path)
    assert "OLDID123" in state
    assert state["OLDID123"][COMP_CHECK_OFFSET] == "checked, looked fine"  # unrenamed -> carries forward
    # Both the obsolete manual "LY Weekday Occ." text and the pre-rename
    # "Notes / Verdict" text are correctly absent -- neither header name
    # exists in the current MANUAL_COLUMNS list.
    assert "65% last year" not in state["OLDID123"]
    assert "great find" not in state["OLDID123"]
    assert state["OLDID123"][LESSON_LEARNED_OFFSET] is None
