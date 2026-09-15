import datetime as dt

from booking_quality_log.compute import BookingRow
from booking_quality_log.workbook_build import (
    FIRST_DATA_ROW,
    HEADER_ROW,
    HEADERS,
    HIDDEN_COLUMNS,
    MANUAL_COLS_COUNT,
    SHEET_NAME,
    build_booking_quality_sheet,
    build_read_me_sheet,
    new_workbook,
)


def _row(res_id, checkin=dt.date(2026, 9, 5)):
    return BookingRow(
        property_name="Test Property",
        check_in=checkin,
        check_out=checkin + dt.timedelta(days=2),
        nights=2,
        stay_pattern="Weekend-anchored",
        one_night_stay=False,
        booked_date=checkin - dt.timedelta(days=10),
        booking_window_days=10,
        bw_vs_median="Typical",
        my_adr=400.0,
        my_revenue=800.0,
        source="airbnb",
        target_adr_p75=380.0,
        vs_target_dollar=20.0,
        vs_target_pct=0.0526,
        market_p25=250.0,
        market_p90=420.0,
        stly_adr="no data",
        ly_occ="20%, 65%",
        demand_tier="High",
        gap_before_days="first known booking in window",
        gap_before_signal=None,
        gap_after_days=1,
        gap_after_signal="Upsell candidate (rarely fills alone)",
        status="Confirmed",
        reservation_id=res_id,
    )


def test_sheet_structure_matches_prototype_layout():
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1))
    ws = wb[SHEET_NAME]

    header_values = [c.value for c in ws[HEADER_ROW]]
    assert header_values == HEADERS
    assert len(HEADERS) == 33  # A..AG
    assert "Status" in HEADERS
    assert "Reservation ID" in HEADERS
    assert MANUAL_COLS_COUNT == 5

    assert ws.column_dimensions["AB"].hidden is True
    assert HIDDEN_COLUMNS == {"AB"}

    data_row = ws[FIRST_DATA_ROW]
    assert data_row[0].value == "Test Property"
    assert data_row[26].value == "Confirmed"  # AA: Status
    assert data_row[27].value == "AAA111"  # AB: Reservation ID


def test_manual_notes_carried_forward_by_reservation_id():
    wb = new_workbook()
    prior_notes = {"AAA111": ("checked", "5%", "yes", "ok", "looks good")}
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1), manual_notes=prior_notes)
    ws = wb[SHEET_NAME]
    row = ws[FIRST_DATA_ROW]
    manual_values = [c.value for c in row[28:33]]
    assert manual_values == list(prior_notes["AAA111"])


def test_manual_notes_blank_for_a_row_with_no_prior_match():
    wb = new_workbook()
    build_booking_quality_sheet(
        wb, [_row("NEWID")], dt.date(2026, 9, 1), manual_notes={"SOMEOTHERID": ("x",) * 5}
    )
    ws = wb[SHEET_NAME]
    row = ws[FIRST_DATA_ROW]
    manual_values = [c.value for c in row[28:33]]
    assert manual_values == [None] * 5


def test_cancelled_row_is_grayed_out_and_shows_status():
    wb = new_workbook()
    row = _row("CANCELLED1")
    row.status = "Cancelled"
    row.gap_before_days = "n/a (cancelled)"
    row.gap_after_days = "n/a (cancelled)"
    build_booking_quality_sheet(wb, [row], dt.date(2026, 9, 1))
    ws = wb[SHEET_NAME]
    data_row = ws[FIRST_DATA_ROW]
    assert data_row[26].value == "Cancelled"


def test_ly_occ_column_present_and_computed():
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1))
    ws = wb[SHEET_NAME]
    assert "LY occ.\n(per night)" in HEADERS
    data_row = ws[FIRST_DATA_ROW]
    assert data_row[20].value == "20%, 65%"  # U: LY occ. (per night)


def test_read_me_sheet_created():
    wb = new_workbook()
    build_read_me_sheet(wb)
    assert "Read Me" in wb.sheetnames
    assert wb["Read Me"]["A1"].value == "How to read this log"
