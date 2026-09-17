import datetime as dt

from booking_quality_log.compute import (
    START_DATE,
    build_booking_rows,
    demand_tier_bucket,
    fill_difficulty_note,
)
from booking_quality_log.reservations import Reservation
from booking_quality_log.market import MarketDay


def _res(res_id, check_in, check_out, adr, revenue, booked_date, confirmation_code, status="booked", guest_count=None):
    return Reservation(
        reservation_id=res_id,
        listing_name="Test Property",
        check_in=check_in,
        check_out=check_out,
        adr=adr,
        revenue=revenue,
        booked_date=booked_date,
        booking_channel="airbnb",
        booking_status=status,
        confirmation_code=confirmation_code,
        guest_count=guest_count,
    )


def _market_day(p75=380, occupancy=70, occupancy_stly=40, p25=250, p90=420):
    return MarketDay(p25=p25, p50=300, p75=p75, p90=p90, occupancy_stly=occupancy_stly, occupancy=occupancy)


def test_only_confirmed_and_in_window_bookings_become_rows():
    res = [
        _res("r0", dt.date(2026, 8, 25), dt.date(2026, 8, 28), 300, 900, dt.date(2026, 8, 1), "OLD"),
        _res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 7), 400, 800, dt.date(2026, 8, 20), "AAA111"),
    ]
    market = {dt.date(2026, 9, 5): _market_day(), dt.date(2026, 9, 6): _market_day()}
    rows = build_booking_rows("Test Property", res, market)
    assert len(rows) == 1
    assert rows[0].check_in == dt.date(2026, 9, 5) >= START_DATE


def test_gap_signals_1_night_upsell_2_night_los_discount():
    res = [
        _res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 7), 400, 800, dt.date(2026, 8, 20), "A1"),
        _res("r2", dt.date(2026, 9, 8), dt.date(2026, 9, 9), 250, 250, dt.date(2026, 9, 8), "B2"),  # 1-night gap before
        _res("r3", dt.date(2026, 9, 11), dt.date(2026, 9, 14), 350, 1050, dt.date(2026, 7, 1), "C3"),  # 2-night gap before
    ]
    market = {
        dt.date(2026, 9, d): _market_day(occupancy=(20 if d == 7 else (45 if d in (9, 10) else 65)))
        for d in range(5, 14)
    }
    rows = build_booking_rows("Test Property", res, market)
    r1, r2, r3 = rows

    assert r1.gap_after_days == 1
    assert r1.gap_after_signal == "Upsell candidate (rarely fills alone)"
    assert r2.gap_before_days == 1
    assert r2.gap_before_signal == "Upsell candidate (rarely fills alone)"

    assert r2.gap_after_days == 2
    assert r2.gap_after_signal == "LOS-discount candidate (sometimes fills alone)"
    assert r3.gap_before_days == 2
    assert r3.gap_before_signal == "LOS-discount candidate (sometimes fills alone)"


def test_no_signal_for_gaps_other_than_1_or_2_nights():
    res = [
        _res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1"),
        _res("r2", dt.date(2026, 9, 10), dt.date(2026, 9, 11), 400, 400, dt.date(2026, 8, 20), "A2"),  # 4-night gap
    ]
    market = {}
    rows = build_booking_rows("Test Property", res, market)
    assert rows[0].gap_after_days == 4
    assert rows[0].gap_after_signal is None


def test_edge_of_pulled_window_gets_text_note_not_numeric_gap():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    rows = build_booking_rows("Test Property", res, {})
    assert rows[0].gap_before_days == "first known booking in window"
    assert rows[0].gap_after_days == "last known booking in window"
    assert rows[0].gap_before_signal is None
    assert rows[0].gap_after_signal is None


def test_stay_pattern_and_one_night_flag():
    res = [
        _res("r1", dt.date(2026, 9, 7), dt.date(2026, 9, 9), 300, 600, dt.date(2026, 8, 1), "A1"),  # Mon-Wed, midweek
        _res("r2", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 300, 300, dt.date(2026, 8, 1), "A2"),  # Saturday, weekend-anchored + 1-night
    ]
    rows = build_booking_rows("Test Property", res, {})
    by_id = {r.reservation_id: r for r in rows}
    assert by_id["A1"].stay_pattern == "Midweek"
    assert by_id["A1"].one_night_stay is False
    assert by_id["A2"].stay_pattern == "Weekend-anchored"
    assert by_id["A2"].one_night_stay is True


def test_target_adr_and_vs_target_use_p75():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    market = {dt.date(2026, 9, 5): _market_day(p75=380)}
    row = build_booking_rows("Test Property", res, market)[0]
    assert row.target_adr_p75 == 380
    assert row.vs_target_dollar == 20
    assert row.vs_target_pct == round(20 / 380, 4)


def test_target_adr_blank_when_no_comp_set_data():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.target_adr_p75 is None
    assert row.vs_target_dollar == "n/a"
    assert row.vs_target_pct == "n/a"


def test_demand_tier_buckets():
    assert demand_tier_bucket(10) == "Low"
    assert demand_tier_bucket(45) == "Mid"
    assert demand_tier_bucket(80) == "High"
    assert demand_tier_bucket(None) == ""


def test_fill_difficulty_notes():
    assert fill_difficulty_note(10) == "rarely fills alone"
    assert fill_difficulty_note(45) == "sometimes fills alone"
    assert fill_difficulty_note(80) == "usually fills alone"


def test_bw_vs_median_far_out_last_minute_typical():
    res = [
        _res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 300, 300, dt.date(2026, 8, 25), "A1"),  # BW 11
        _res("r2", dt.date(2026, 9, 8), dt.date(2026, 9, 9), 300, 300, dt.date(2026, 9, 7), "A2"),  # BW 1 (last-minute)
        _res("r3", dt.date(2026, 9, 20), dt.date(2026, 9, 21), 300, 300, dt.date(2026, 5, 1), "A3"),  # BW ~142 (far out)
    ]
    rows = build_booking_rows("Test Property", res, {})
    by_id = {r.reservation_id: r for r in rows}
    assert by_id["A2"].bw_vs_median == "Last-minute"
    assert by_id["A3"].bw_vs_median == "Far out"


def test_stly_adr_looks_up_same_calendar_date_last_year():
    res = [
        _res("ly1", dt.date(2025, 9, 5), dt.date(2025, 9, 6), 250, 250, dt.date(2025, 8, 1), "LY1"),
        _res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1"),
    ]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.stly_adr == 250


def test_stly_adr_no_data_when_no_match():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.stly_adr == "no data"


def test_reservation_id_prefers_confirmation_code():
    res = [_res("internal-uuid-123", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "HMT5EBPQ54")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.reservation_id == "HMT5EBPQ54"


def test_confirmed_rows_marked_confirmed():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.status == "Confirmed"


def test_cancelled_booking_still_gets_a_row_marked_cancelled():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1", status="cancelled")]
    rows = build_booking_rows("Test Property", res, {})
    assert len(rows) == 1
    assert rows[0].status == "Cancelled"


def test_cancelled_booking_gap_fields_are_not_applicable():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1", status="cancelled")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.gap_before_days == "n/a (cancelled)"
    assert row.gap_before_signal is None
    assert row.gap_after_days == "n/a (cancelled)"
    assert row.gap_after_signal is None


def test_cancelled_booking_does_not_affect_confirmed_neighbors_gaps():
    res = [
        _res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1"),
        _res("r2", dt.date(2026, 9, 7), dt.date(2026, 9, 8), 400, 400, dt.date(2026, 8, 20), "A2", status="cancelled"),
        _res("r3", dt.date(2026, 9, 11), dt.date(2026, 9, 12), 400, 400, dt.date(2026, 8, 20), "A3"),
    ]
    rows = build_booking_rows("Test Property", res, {})
    r1 = next(r for r in rows if r.reservation_id == "A1")
    r3 = next(r for r in rows if r.reservation_id == "A3")
    # The cancelled r2 doesn't count as a calendar neighbor -- r1 and r3
    # are adjacent confirmed bookings with a 5-night gap between them.
    assert r1.gap_after_days == 5
    assert r3.gap_before_days == 5


def test_ly_occ_shown_per_night_not_averaged():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 7), 400, 800, dt.date(2026, 8, 20), "A1")]
    market = {
        dt.date(2026, 9, 5): _market_day(occupancy_stly=20),
        dt.date(2026, 9, 6): _market_day(occupancy_stly=65),
    }
    row = build_booking_rows("Test Property", res, market)[0]
    assert row.ly_occ == "20%, 65%"


def test_ly_occ_no_data_when_market_has_no_stly_occupancy():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.ly_occ == "no data"


def test_ly_occ_partial_coverage_shows_no_data_per_missing_night():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 7), 400, 800, dt.date(2026, 8, 20), "A1")]
    market = {dt.date(2026, 9, 5): _market_day(occupancy_stly=20)}  # 9/6 missing
    row = build_booking_rows("Test Property", res, market)[0]
    assert row.ly_occ == "20%, no data"


def test_cancelled_booking_still_computed_target_adr_and_demand_tier():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1", status="cancelled")]
    market = {dt.date(2026, 9, 5): _market_day(p75=380, occupancy=70)}
    row = build_booking_rows("Test Property", res, market)[0]
    assert row.target_adr_p75 == 380
    assert row.demand_tier == "High"


def test_my_season_adr_not_enough_data_with_thin_history():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.my_season_adr == "not enough data"
    assert row.vs_my_season_pct == "n/a"


def test_my_season_adr_pools_same_month_and_day_category_across_years():
    # Three prior Saturdays in September (2023-2025), all weekend-anchored
    # like the booking under test -- enough history for a band.
    res = [
        _res("ly1", dt.date(2023, 9, 2), dt.date(2023, 9, 3), 280, 280, dt.date(2023, 8, 1), "LY1"),
        _res("ly2", dt.date(2024, 9, 7), dt.date(2024, 9, 8), 300, 300, dt.date(2024, 8, 1), "LY2"),
        _res("ly3", dt.date(2025, 9, 6), dt.date(2025, 9, 7), 320, 320, dt.date(2025, 8, 1), "LY3"),
        _res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1"),  # Saturday
    ]
    row = build_booking_rows("Test Property", res, {})[0]
    assert "not enough data" not in row.my_season_adr
    assert "n=3" in row.my_season_adr
    # median of 280/300/320 is 300 -> this booking's $400 is +33.3% vs season
    assert row.vs_my_season_pct == round((400 - 300) / 300, 4)


def test_my_season_adr_only_pools_matching_day_category():
    # A midweek historical night in the same month must NOT count toward a
    # weekend-anchored booking's season band, and vice versa.
    res = [
        _res("ly1", dt.date(2025, 9, 2), dt.date(2025, 9, 3), 200, 200, dt.date(2025, 8, 1), "LY1"),  # Tue, midweek
        _res("ly2", dt.date(2025, 9, 9), dt.date(2025, 9, 10), 210, 210, dt.date(2025, 8, 1), "LY2"),  # Tue, midweek
        _res("ly3", dt.date(2025, 9, 16), dt.date(2025, 9, 17), 220, 220, dt.date(2025, 8, 1), "LY3"),  # Tue, midweek
        _res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1"),  # Saturday
    ]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.my_season_adr == "not enough data"


def test_override_notes_pulled_for_stay_dates():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 7), 400, 800, dt.date(2026, 8, 20), "A1")]
    overrides_by_date = {
        dt.date(2026, 9, 5): "9/1 - Pacing behind by -10%",
        dt.date(2026, 9, 6): "9/1 - LY below 30%",
    }
    row = build_booking_rows("Test Property", res, {}, overrides_by_date=overrides_by_date)[0]
    assert row.override_notes == "9/1 - Pacing behind by -10%; 9/1 - LY below 30%"


def test_override_notes_empty_when_none_active():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.override_notes == ""


def test_override_notes_dedups_repeated_reason():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 7), 400, 800, dt.date(2026, 8, 20), "A1")]
    overrides_by_date = {
        dt.date(2026, 9, 5): "9/1 - Pacing behind by -10%",
        dt.date(2026, 9, 6): "9/1 - Pacing behind by -10%",
    }
    row = build_booking_rows("Test Property", res, {}, overrides_by_date=overrides_by_date)[0]
    assert row.override_notes == "9/1 - Pacing behind by -10%"


def test_guest_count_flows_through_to_row():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1", guest_count=7)]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.guest_count == 7


def test_guest_count_none_when_not_provided():
    res = [_res("r1", dt.date(2026, 9, 5), dt.date(2026, 9, 6), 400, 400, dt.date(2026, 8, 20), "A1")]
    row = build_booking_rows("Test Property", res, {})[0]
    assert row.guest_count is None
