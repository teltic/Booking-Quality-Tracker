import datetime as dt

from booking_quality_log.reservations import _from_api_rows


def _raw_row(**overrides):
    row = {
        "reservation_id": "r1",
        "listing_name": "Test Property",
        "check_in": "2026-09-05",
        "check_out": "2026-09-07",
        "booking_status": "booked",
        "rental_revenue": "400",
        "no_of_days": 2,
        "booked_date": "2026-08-20",
        "booking_channel": "airbnb",
        "channelConfirmationCode": "AAA111",
    }
    row.update(overrides)
    return row


def test_guest_count_parsed_as_int():
    [r] = _from_api_rows([_raw_row(guest_count=7)])
    assert r.guest_count == 7


def test_guest_count_none_when_missing():
    [r] = _from_api_rows([_raw_row()])
    assert r.guest_count is None


def test_guest_count_none_when_unparseable():
    [r] = _from_api_rows([_raw_row(guest_count="not-a-number")])
    assert r.guest_count is None


def test_guest_count_coerced_from_string():
    [r] = _from_api_rows([_raw_row(guest_count="12")])
    assert r.guest_count == 12
