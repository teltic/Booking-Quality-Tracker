import datetime as dt

from booking_quality_log.compute import BookingRow
from booking_quality_log.workbook_build import (
    FIRST_DATA_ROW,
    HEADER_ROW,
    HEADERS,
    HIDDEN_COLUMNS,
    MANUAL_COLS_COUNT,
    MANUAL_COLUMNS,
    MANUAL_FIELDS,
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
        my_season_adr="$310 ($295-$340, n=4)",
        vs_my_season_pct=0.29,
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
        override_notes="9/1 - Pacing behind by -10%",
    )


def test_sheet_structure_matches_layout():
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1))
    ws = wb[SHEET_NAME]

    header_values = [c.value for c in ws[HEADER_ROW]]
    assert header_values == HEADERS
    assert len(HEADERS) == 42  # A..AP
    assert "Status" in HEADERS
    assert "Reservation ID" in HEADERS
    assert MANUAL_COLS_COUNT == 11

    assert ws.column_dimensions["AD"].hidden is True
    assert HIDDEN_COLUMNS == {"AD"}

    data_row = ws[FIRST_DATA_ROW]
    assert data_row[0].value == "Test Property"
    assert data_row[17].value == "$310 ($295-$340, n=4)"  # R: My Season ADR
    assert abs(data_row[18].value - 0.29) < 1e-9  # S: vs My Season (%)
    assert data_row[28].value == "Confirmed"  # AC: Status
    assert data_row[29].value == "AAA111"  # AD: Reservation ID
    assert data_row[30].value == "9/1 - Pacing behind by -10%"  # AE: Override Notes


def test_manual_notes_carried_forward_by_reservation_id():
    wb = new_workbook()
    prior_notes = {"AAA111": tuple(f"val{i}" for i in range(MANUAL_COLS_COUNT))}
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1), manual_notes=prior_notes)
    ws = wb[SHEET_NAME]
    row = ws[FIRST_DATA_ROW]
    manual_values = [c.value for c in row[31 : 31 + MANUAL_COLS_COUNT]]
    assert manual_values == list(prior_notes["AAA111"])


def test_manual_notes_blank_for_a_row_with_no_prior_match():
    wb = new_workbook()
    build_booking_quality_sheet(
        wb, [_row("NEWID")], dt.date(2026, 9, 1),
        manual_notes={"SOMEOTHERID": ("x",) * MANUAL_COLS_COUNT},
    )
    ws = wb[SHEET_NAME]
    row = ws[FIRST_DATA_ROW]
    manual_values = [c.value for c in row[31 : 31 + MANUAL_COLS_COUNT]]
    assert manual_values == [None] * MANUAL_COLS_COUNT


def test_manual_columns_match_manual_fields_order():
    assert MANUAL_COLUMNS == [name for name, _kind, _opts in MANUAL_FIELDS]
    assert MANUAL_COLUMNS == [
        "Comp Check (Airbnb)", "ADR vs Comp Rating", "Demand-ADR Fit",
        "Airbnb LOS Rule", "LOS / Window Fit", "LOS Discount % (blended)",
        "Primary Lever", "Pacing Push %", "Final PL Check", "Verdict",
        "Lesson Learned",
    ]


def test_dropdown_validation_added_for_each_dropdown_field():
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111"), _row("BBB222")], dt.date(2026, 9, 1))
    ws = wb[SHEET_NAME]

    dropdown_count = sum(1 for _name, kind, _opts in MANUAL_FIELDS if kind == "dropdown")
    assert len(ws.data_validations.dataValidation) == dropdown_count

    verdict_dv = next(
        dv for dv in ws.data_validations.dataValidation
        if "Win" in dv.formula1 and "Loss" in dv.formula1
    )
    assert "Too Early to Tell" in verdict_dv.formula1
    # Applied to both data rows, not just the header or a single cell.
    assert any(str(cr).startswith("AO5") for cr in verdict_dv.sqref.ranges) or "AO5:AO6" in str(verdict_dv.sqref)


def test_cancelled_row_is_grayed_out_and_shows_status():
    wb = new_workbook()
    row = _row("CANCELLED1")
    row.status = "Cancelled"
    row.gap_before_days = "n/a (cancelled)"
    row.gap_after_days = "n/a (cancelled)"
    build_booking_quality_sheet(wb, [row], dt.date(2026, 9, 1))
    ws = wb[SHEET_NAME]
    data_row = ws[FIRST_DATA_ROW]
    assert data_row[28].value == "Cancelled"


def test_ly_occ_column_present_and_computed():
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1))
    ws = wb[SHEET_NAME]
    assert "LY occ.\n(per night)" in HEADERS
    data_row = ws[FIRST_DATA_ROW]
    assert data_row[22].value == "20%, 65%"  # W: LY occ. (per night)


def test_manual_percent_fields_get_display_suffix_not_true_percent_format():
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1))
    ws = wb[SHEET_NAME]
    los_discount_col = 31 + MANUAL_COLUMNS.index("LOS Discount % (blended)") + 1
    pacing_push_col = 31 + MANUAL_COLUMNS.index("Pacing Push %") + 1
    assert ws.cell(row=FIRST_DATA_ROW, column=los_discount_col).number_format == '0.0"%"'
    assert ws.cell(row=FIRST_DATA_ROW, column=pacing_push_col).number_format == '0.0"%"'


def test_read_me_sheet_created():
    wb = new_workbook()
    build_read_me_sheet(wb)
    assert "Read Me" in wb.sheetnames
    assert wb["Read Me"]["A1"].value == "How to read this log"
