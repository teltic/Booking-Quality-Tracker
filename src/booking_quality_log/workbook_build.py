"""Build the "Booking Quality Log" workbook with openpyxl.

Column order, widths, number formats and conditional-formatting colors are
reproduced from the original hand-built prototype workbook so a rerun looks
like the same tool, just automated.
"""

from __future__ import annotations

import datetime as dt

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .compute import BookingRow

SHEET_NAME = "Booking Quality Log"

# openpyxl colors are 8-digit ARGB; the leading 2 digits are alpha
# (opacity) -- a plain 6-digit RGB string silently becomes "00" (fully
# transparent), so every color below carries an explicit "FF" (opaque)
# prefix. Separately, Excel has an undocumented quirk specific to
# conditional-formatting fills (differential styles / dxfs): a plain cell
# fill uses PatternFill("solid", fgColor=...), but a fill used inside a
# FormulaRule needs PatternFill(bgColor=...) with NO patternType instead --
# Excel reads the swatch from bgColor there, not fgColor -- confirmed the
# hard way against real Excel. FILL_HEADER is a plain cell fill, so it keeps
# "solid" + fgColor; everything else here is only ever used inside a
# FormulaRule, so it uses the bgColor-only dxf form.
FILL_HEADER = PatternFill("solid", fgColor="FFD9E1F2")
BOLD = Font(bold=True)
TITLE_FONT = Font(bold=True, size=14)

# vs-Target 8-tier green (above target) / amber (below target) scale,
# colors matched exactly to the original workbook's differential styles.
FILL_TARGET_TIERS = [
    PatternFill(bgColor="FF1A7F4B"),  # >= +50%
    PatternFill(bgColor="FF3FAE6E"),  # +25% to +50%
    PatternFill(bgColor="FF8FD19E"),  # +10% to +25%
    PatternFill(bgColor="FFD6EFDA"),  # 0% to +10%
    PatternFill(bgColor="FFFCE0A6"),  # -10% to 0%
    PatternFill(bgColor="FFF7C97A"),  # -25% to -10%
    PatternFill(bgColor="FFF0AA4D"),  # -50% to -25%
    PatternFill(bgColor="FFE08A2B"),  # < -50%
]
FILL_FLAG_NOTE = PatternFill(bgColor="FFFCEBC9")  # Midweek / 1-Night Stay
FILL_UPSELL = PatternFill(bgColor="FFE4D9F2")  # Gap signal: Upsell candidate
FILL_LOS_DISCOUNT = PatternFill(bgColor="FFD9E9F2")  # Gap signal: LOS-discount
FILL_CANCELLED = PatternFill(bgColor="FFE7E6E6")  # Status = Cancelled (whole row grayed out)

HEADERS = [
    "Property", "Check-in", "In Day", "Check-out", "Out Day", "Nights",
    "Stay Pattern", "1-Night\nStay", "Booked", "Booking\nWindow (d)",
    "BW vs\nMedian", "My ADR", "My Revenue", "Source", "Target ADR\n(P75)",
    "vs Target\n($)", "vs Target\n(%)", "Market\nP25", "Market\nP90",
    "STLY ADR\n(same dates)", "LY occ.\n(per night)", "Demand Tier\n(stay dates)",
    "Gap Before\n(d)", "Gap Before Signal", "Gap After\n(d)", "Gap After Signal",
    "Status", "Reservation ID", "Comp Check (Airbnb)",
    "Pacing Push %", "LOS Discount", "Final PL Check", "Notes / Verdict",
]

# Column numbers (1-indexed) for every column referenced by name below --
# defined once here, letters derived with get_column_letter(), so a future
# column insertion/removal only ever means editing HEADERS + this block,
# never hunting down hardcoded letter strings scattered through formulas.
COL_STAY_PATTERN = 7
COL_ONE_NIGHT_STAY = 8
COL_TARGET_ADR = 15
COL_VS_TARGET_DOLLAR = 16
COL_VS_TARGET_PCT = 17
COL_GAP_BEFORE_SIGNAL = 24
COL_GAP_AFTER_SIGNAL = 26
STATUS_COL = 27
RESERVATION_ID_COL = 28
MANUAL_COLS_START = 29
MANUAL_COLS_COUNT = 5

assert len(HEADERS) == MANUAL_COLS_START - 1 + MANUAL_COLS_COUNT

HIDDEN_COLUMNS = {get_column_letter(RESERVATION_ID_COL)}

MANUAL_COLUMNS = [
    "Comp Check (Airbnb)", "Pacing Push %",
    "LOS Discount", "Final PL Check", "Notes / Verdict",
]

DATE_COLS = {2, 4}  # Check-in, Check-out
MONEY_COLS = {12, 13, 15, 16, 18, 19}  # My ADR/Revenue, Target ADR, vs Target $, Market P25/P90
HEADER_ROW = 4
FIRST_DATA_ROW = 5

COLUMN_WIDTHS_BY_NUMBER = {
    1: 22, 2: 10, 3: 6, 4: 10, 5: 6, 7: 13, 8: 7, 9: 10, 10: 8, 11: 9,
    12: 8, 13: 9, 17: 8, 20: 10, 21: 16, 23: 8, 24: 26, 25: 8, 26: 26,
    STATUS_COL: 12, RESERVATION_ID_COL: 14, MANUAL_COLS_START: 24,
    MANUAL_COLS_START + 1: 16, MANUAL_COLS_START + 2: 16,
    MANUAL_COLS_START + 3: 20, MANUAL_COLS_START + 4: 26,
}
COLUMN_WIDTHS = {get_column_letter(n): w for n, w in COLUMN_WIDTHS_BY_NUMBER.items()}


def _write_date(ws: Worksheet, row: int, col: int, value: dt.date | None) -> None:
    if value is None:
        return
    ws.cell(row=row, column=col, value=dt.datetime.combine(value, dt.time()))
    ws.cell(row=row, column=col).number_format = "dd-mmm-yy"


def new_workbook() -> Workbook:
    wb = Workbook()
    del wb["Sheet"]
    return wb


def build_booking_quality_sheet(
    wb: Workbook,
    rows: list[BookingRow],
    display_start_date: dt.date,
    manual_notes: dict[str, tuple] | None = None,
) -> None:
    """`manual_notes` maps Reservation ID -> tuple of the 6 manual-column
    values, carried forward from a prior run (see workbook_state.py).
    """
    manual_notes = manual_notes or {}
    ws = wb.create_sheet(SHEET_NAME)

    title_cell = ws.cell(row=1, column=1, value="Booking Quality Log — Mesquite Properties")
    title_cell.font = TITLE_FONT
    ws.cell(
        row=2,
        column=1,
        value=(
            f"Showing check-ins from {display_start_date.isoformat()} onward, sorted by "
            "Booked date (newest first). Both properties set to Premium tier — target line "
            "is the 75th percentile of the comp set, not the median. Raw signals only, no "
            "verdict. See 'Read Me' tab."
        ),
    )

    for col_idx, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=HEADER_ROW, column=col_idx, value=header)
        cell.font = BOLD
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(wrap_text=True, vertical="bottom")
    ws.freeze_panes = f"A{FIRST_DATA_ROW}"

    for r, row in enumerate(rows, start=FIRST_DATA_ROW):
        ws.cell(row=r, column=1, value=row.property_name)
        _write_date(ws, r, 2, row.check_in)
        ws.cell(row=r, column=3, value=row.check_in.strftime("%a"))
        _write_date(ws, r, 4, row.check_out)
        ws.cell(row=r, column=5, value=row.check_out.strftime("%a"))
        ws.cell(row=r, column=6, value=row.nights)
        ws.cell(row=r, column=7, value=row.stay_pattern)
        ws.cell(row=r, column=8, value="Yes" if row.one_night_stay else None)
        _write_date(ws, r, 9, row.booked_date)
        ws.cell(row=r, column=10, value=row.booking_window_days)
        ws.cell(row=r, column=11, value=row.bw_vs_median)
        ws.cell(row=r, column=12, value=row.my_adr)
        ws.cell(row=r, column=13, value=row.my_revenue)
        ws.cell(row=r, column=14, value=row.source)
        ws.cell(row=r, column=15, value=row.target_adr_p75)
        ws.cell(row=r, column=16, value=row.vs_target_dollar)
        ws.cell(row=r, column=17, value=row.vs_target_pct)
        ws.cell(row=r, column=18, value=row.market_p25)
        ws.cell(row=r, column=19, value=row.market_p90)
        ws.cell(row=r, column=20, value=row.stly_adr)
        ws.cell(row=r, column=21, value=row.ly_occ)
        ws.cell(row=r, column=22, value=row.demand_tier)
        ws.cell(row=r, column=23, value=row.gap_before_days)
        ws.cell(row=r, column=COL_GAP_BEFORE_SIGNAL, value=row.gap_before_signal)
        ws.cell(row=r, column=25, value=row.gap_after_days)
        ws.cell(row=r, column=COL_GAP_AFTER_SIGNAL, value=row.gap_after_signal)
        ws.cell(row=r, column=STATUS_COL, value=row.status)
        ws.cell(row=r, column=RESERVATION_ID_COL, value=row.reservation_id)

        saved = manual_notes.get(row.reservation_id)
        for offset in range(MANUAL_COLS_COUNT):
            value = saved[offset] if saved else None
            ws.cell(row=r, column=MANUAL_COLS_START + offset, value=value)

        for col in MONEY_COLS:
            cell = ws.cell(row=r, column=col)
            if cell.value not in (None, "", "n/a"):
                cell.number_format = '$#,##0.00;("$"#,##0.00);\\-'
        pct_cell = ws.cell(row=r, column=17)
        if isinstance(pct_cell.value, (int, float)):
            pct_cell.number_format = "0.0%"

    last_row = len(rows) + FIRST_DATA_ROW - 1
    for letter, width in COLUMN_WIDTHS.items():
        ws.column_dimensions[letter].width = width
    for letter in HIDDEN_COLUMNS:
        ws.column_dimensions[letter].hidden = True

    if last_row >= FIRST_DATA_ROW:
        r0 = FIRST_DATA_ROW

        def col_letter(col_num: int) -> str:
            return get_column_letter(col_num)

        def col_range(col_num: int) -> str:
            letter = col_letter(col_num)
            return f"{letter}{r0}:{letter}{last_row}"

        target_adr_letter = col_letter(COL_TARGET_ADR)
        vs_target_dollar_letter = col_letter(COL_VS_TARGET_DOLLAR)
        vs_target_pct_letter = col_letter(COL_VS_TARGET_PCT)

        # (lower-bound, upper-bound) on the vs-Target ratio for each of the
        # 8 tiers, outermost first; None means "no bound on that side".
        TIER_BOUNDS = [
            (0.5, None), (0.25, 0.5), (0.1, 0.25), (0.0, 0.1),
            (-0.1, 0.0), (-0.25, -0.1), (-0.5, -0.25), (None, -0.5),
        ]
        for (lo, hi), fill in zip(TIER_BOUNDS, FILL_TARGET_TIERS):
            for col_num, ratio_expr in (
                (COL_VS_TARGET_DOLLAR, f"({vs_target_dollar_letter}{r0}/{target_adr_letter}{r0})"),
                (COL_VS_TARGET_PCT, f"{vs_target_pct_letter}{r0}"),
            ):
                letter = col_letter(col_num)
                conds = [f"ISNUMBER({letter}{r0})"]
                if lo is not None:
                    conds.append(f"{ratio_expr}>={lo}")
                if hi is not None:
                    conds.append(f"{ratio_expr}<{hi}")
                formula = f"AND({','.join(conds)})"
                ws.conditional_formatting.add(
                    col_range(col_num), FormulaRule(formula=[formula], fill=fill)
                )

        one_night_letter = col_letter(COL_ONE_NIGHT_STAY)
        stay_pattern_letter = col_letter(COL_STAY_PATTERN)
        ws.conditional_formatting.add(
            col_range(COL_ONE_NIGHT_STAY),
            FormulaRule(formula=[f'{one_night_letter}{r0}="Yes"'], fill=FILL_FLAG_NOTE),
        )
        ws.conditional_formatting.add(
            col_range(COL_STAY_PATTERN),
            FormulaRule(formula=[f'{stay_pattern_letter}{r0}="Midweek"'], fill=FILL_FLAG_NOTE),
        )
        for col_num in (COL_GAP_BEFORE_SIGNAL, COL_GAP_AFTER_SIGNAL):
            letter = col_letter(col_num)
            ws.conditional_formatting.add(
                col_range(col_num),
                FormulaRule(
                    formula=[f'ISNUMBER(SEARCH("Upsell",{letter}{r0}))'],
                    fill=FILL_UPSELL,
                ),
            )
            ws.conditional_formatting.add(
                col_range(col_num),
                FormulaRule(
                    formula=[f'ISNUMBER(SEARCH("LOS-discount",{letter}{r0}))'],
                    fill=FILL_LOS_DISCOUNT,
                ),
            )

        # Gray out the whole visible row when Status = Cancelled, added last
        # (lowest priority) so it never hides a more specific signal color
        # (e.g. a cancelled 1-Night booking still shows its tan highlight).
        status_letter = col_letter(STATUS_COL)
        last_visible_letter = col_letter(COL_GAP_AFTER_SIGNAL)
        ws.conditional_formatting.add(
            f"A{r0}:{last_visible_letter}{last_row}",
            FormulaRule(formula=[f'${status_letter}{r0}="Cancelled"'], fill=FILL_CANCELLED),
        )
        ws.conditional_formatting.add(
            col_range(STATUS_COL),
            FormulaRule(formula=[f'{status_letter}{r0}="Cancelled"'], fill=FILL_CANCELLED),
        )


READ_ME_LINES = [
    ("How to read this log", True),
    ("", False),
    ("Target ADR (P75)", True),
    (
        "Both properties are set to Premium tier, so the benchmark is the comp set's "
        "75th percentile price for the stay dates — not the median. 'vs Target' compares "
        "your ADR to that line. Green = at/above target, in 4 tiers by how far above. "
        "Amber = below target, in 4 tiers by how far below.",
        False,
    ),
    ("", False),
    ("Market P25 / P90", True),
    ("Shown for extra context — how wide the comp set's pricing spread is on those dates.", False),
    ("", False),
    ("STLY ADR", True),
    (
        "Your own ADR from the same calendar dates last year, where a booking existed "
        "then. Coverage is thin since it depends on you having had a booking on that "
        "exact date last year — treat it as a bonus data point, not a column you'll "
        "always have.",
        False,
    ),
    ("", False),
    ("LY occ. (per night)", True),
    (
        "Comp-set market occupancy on the same calendar dates last year, shown one value "
        "per night of the stay rather than averaged -- a 2-night stay might show '20%, "
        "65%' rather than a single blended 42%, so a night that historically struggles to "
        "fill doesn't get smoothed away by a strong neighboring night. 'no data' means "
        "PriceLabs didn't have comp-set data that far back for that specific date.",
        False,
    ),
    ("", False),
    ("Demand Tier", True),
    (
        "Comp-set market occupancy on the stay dates, bucketed Low (<30%), Mid (30-60%), "
        "High (60%+). Use this alongside Booking Window: booked far out on a "
        "High-demand date should carry a premium ADR; a lower ADR is more defensible "
        "on Low-demand dates.",
        False,
    ),
    ("", False),
    ("BW vs Median", True),
    (
        "Compares this booking's lead time to that property's own median booking "
        "window across all its bookings. 'Far out' = booked well ahead of typical; "
        "'Last-minute' = booked well after typical.",
        False,
    ),
    ("", False),
    ("Stay Pattern", True),
    (
        "'Midweek' means no Friday or Saturday night is included in the stay — flagged "
        "since these don't fit typical weekend demand. Use the ADR columns alongside it "
        "to judge whether the price justified the pattern.",
        False,
    ),
    ("", False),
    ("1-Night Stay", True),
    ("Flagged on its own regardless of price or surrounding gaps — your 'fall-out' booking case.", False),
    ("", False),
    ("Gap Before / After Signal", True),
    (
        "1-night gap = Upsell candidate (pitch an extra night to the adjacent guest). "
        "2-night gap = LOS-discount candidate (loosen minimum-stay or discount to "
        "attract a short booking). The fill-difficulty note in parentheses comes from "
        "comp-set occupancy on those specific gap dates.",
        False,
    ),
    ("", False),
    ("Status", True),
    (
        "Confirmed or Cancelled. A booking that gets cancelled after you've already "
        "reviewed it stays on the log (grayed out) instead of disappearing — so a note "
        "you typed on it isn't lost, and a cancelled high- or low-ADR booking is still "
        "there to learn from. Gap Before/After don't apply to a cancelled booking (it no "
        "longer holds any calendar space), so those show 'n/a (cancelled)' instead of a "
        "number. A cancellation by itself never triggers a new file being written — only "
        "a brand-new confirmed booking does.",
        False,
    ),
    ("", False),
    ("Manual note columns", True),
    (
        "Comp Check (Airbnb), Pacing Push %, LOS Discount, Final PL Check, and "
        "Notes/Verdict are blank on purpose — type your own findings in as you review, "
        "the same way you already do it by hand. They're matched to each row by a hidden "
        "Reservation ID column, so a refresh won't wipe out what you've typed — it "
        "carries notes forward for any booking still in view.",
        False,
    ),
    ("", False),
    ("How this refreshes", True),
    (
        "Runs automatically once a day (Windows Task Scheduler). If there's at least "
        "one brand-new confirmed booking since the last run, it writes a new dated "
        "file and re-pulls bookings and comp-set data from PriceLabs, recomputing "
        "every row and signal; if nothing new booked, today is skipped and no file is "
        "written. See README.md for the schedule/setup.",
        False,
    ),
]


def build_read_me_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Read Me")
    ws.column_dimensions["A"].width = 110
    for r, (text, is_bold) in enumerate(READ_ME_LINES, start=1):
        cell = ws.cell(row=r, column=1, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if is_bold:
            cell.font = Font(bold=True, size=13 if r == 1 else 11)
