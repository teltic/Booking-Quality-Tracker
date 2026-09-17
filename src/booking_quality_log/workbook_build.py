"""Build the "Booking Quality Log" workbook with openpyxl.

Column order, widths, number formats and conditional-formatting colors are
reproduced from the original hand-built prototype workbook so a rerun looks
like the same tool, just automated -- with a much deeper manual-review
block (see MANUAL_COLUMNS) added afterward at Thomas's request, aimed at
building up enough structured, rateable data points across many bookings
to start finding real pricing/LOS-discount/pacing-push patterns rather
than one-off notes.
"""

from __future__ import annotations

import datetime as dt

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
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
    "Property", "Check-in", "In Day", "Check-out", "Out Day", "Nights", "Guests",
    "Stay Pattern", "1-Night\nStay", "Booked", "Booking\nWindow (d)",
    "BW vs\nMedian", "My ADR", "My Revenue", "Source", "Target ADR\n(P75)",
    "vs Target\n($)", "vs Target\n(%)", "My Season ADR\n(band)", "vs My\nSeason (%)",
    "Market\nP25", "Market\nP90", "STLY ADR\n(same dates)", "LY occ.\n(per night)",
    "Demand Tier\n(stay dates)", "Gap Before\n(d)", "Gap Before Signal",
    "Gap After\n(d)", "Gap After Signal", "Status", "Reservation ID",
    "Override Notes\n(PriceLabs)",
    "Comp Check (Airbnb)", "ADR vs Comp Rating", "Demand-ADR Fit",
    "Airbnb LOS Rule", "LOS / Window Fit", "LOS Discount % (blended)",
    "Primary Lever", "Pacing Push %", "Final PL Check", "Verdict",
    "Lesson Learned",
]

# Column numbers (1-indexed) for every column referenced by name below --
# defined once here, letters derived with get_column_letter(), so a future
# column insertion/removal only ever means editing HEADERS + this block,
# never hunting down hardcoded letter strings scattered through formulas.
COL_GUESTS = 7
COL_STAY_PATTERN = 8
COL_ONE_NIGHT_STAY = 9
COL_TARGET_ADR = 16
COL_VS_TARGET_DOLLAR = 17
COL_VS_TARGET_PCT = 18
COL_MY_SEASON_ADR = 19
COL_VS_MY_SEASON_PCT = 20
COL_MARKET_P25 = 21
COL_MARKET_P90 = 22
COL_GAP_BEFORE_SIGNAL = 27
COL_GAP_AFTER_SIGNAL = 29
STATUS_COL = 30
RESERVATION_ID_COL = 31
COL_OVERRIDE_NOTES = 32
MANUAL_COLS_START = 33
MANUAL_COLS_COUNT = 11

assert len(HEADERS) == MANUAL_COLS_START - 1 + MANUAL_COLS_COUNT

HIDDEN_COLUMNS = {get_column_letter(RESERVATION_ID_COL)}

# In MANUAL_COLS_START order. Each entry is (header text, kind, options-or-None).
# kind: "text" (free-typed), "number" (plain number, manual), or "dropdown"
# (Excel data-validation list -- a click instead of typing, kept consistent
# for pivoting/filtering once there are enough rows to look for patterns).
MANUAL_FIELDS = [
    ("Comp Check (Airbnb)", "text", None),
    ("ADR vs Comp Rating", "dropdown", ["Above Comp", "At Comp", "Below Comp", "Comp Has No Real Strategy"]),
    ("Demand-ADR Fit", "dropdown", ["Great", "OK", "Underpriced", "Overpriced"]),
    ("Airbnb LOS Rule", "dropdown", ["Sun-Wed Aggressive", "Sun-Wed Minimal", "Sun-Wed Moderate", "None Active"]),
    ("LOS / Window Fit", "dropdown", ["Ideal", "Acceptable", "Suboptimal"]),
    ("LOS Discount % (blended)", "number", None),
    ("Primary Lever", "dropdown", ["Price", "Min Stay", "LOS Discount", "Pacing Push", "Organic-Unclear"]),
    ("Pacing Push %", "number", None),
    ("Final PL Check", "text", None),
    ("Verdict", "dropdown", ["Win", "Loss", "Neutral", "Too Early to Tell"]),
    ("Lesson Learned", "text", None),
]
assert len(MANUAL_FIELDS) == MANUAL_COLS_COUNT
assert [f[0] for f in MANUAL_FIELDS] == HEADERS[MANUAL_COLS_START - 1 :]

MANUAL_COLUMNS = [name for name, _kind, _options in MANUAL_FIELDS]

# Manual numeric fields get a "9.0%" *display suffix* rather than Excel's
# true "0.0%" percentage format -- a real percentage format multiplies the
# stored value by 100 for display, so typing a plain "9" (meaning 9%)
# would show as "900%" unless you remember to type 0.09 instead. This
# keeps typing "9" showing "9.0%" with no gotcha.
MANUAL_PERCENT_SUFFIX_COLS = {
    MANUAL_COLS_START + i for i, (_name, kind, _opts) in enumerate(MANUAL_FIELDS)
    if kind == "number"
}

DATE_COLS = {2, 4}  # Check-in, Check-out
MONEY_COLS = {13, 14, COL_TARGET_ADR, COL_VS_TARGET_DOLLAR, COL_MARKET_P25, COL_MARKET_P90}
PCT_COLS = {COL_VS_TARGET_PCT, COL_VS_MY_SEASON_PCT}  # true fractional percentages (0.05 = 5%)
HEADER_ROW = 4
FIRST_DATA_ROW = 5

COLUMN_WIDTHS_BY_NUMBER = {
    1: 22, 2: 10, 3: 6, 4: 10, 5: 6, COL_GUESTS: 8, COL_STAY_PATTERN: 13,
    COL_ONE_NIGHT_STAY: 7, 10: 10, 11: 8, 12: 9, 13: 8, 14: 9, 18: 8,
    COL_MY_SEASON_ADR: 22, COL_VS_MY_SEASON_PCT: 8, 23: 10, 24: 16,
    26: 8, 27: 26, 28: 8, COL_GAP_AFTER_SIGNAL: 26,
    STATUS_COL: 12, RESERVATION_ID_COL: 14,
    COL_OVERRIDE_NOTES: 26, MANUAL_COLS_START: 24, MANUAL_COLS_START + 1: 22,
    MANUAL_COLS_START + 2: 16, MANUAL_COLS_START + 3: 20, MANUAL_COLS_START + 4: 16,
    MANUAL_COLS_START + 5: 14, MANUAL_COLS_START + 6: 16, MANUAL_COLS_START + 7: 12,
    MANUAL_COLS_START + 8: 20, MANUAL_COLS_START + 9: 16, MANUAL_COLS_START + 10: 28,
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
    """`manual_notes` maps Reservation ID -> tuple of MANUAL_COLUMNS values
    (same order as MANUAL_FIELDS), carried forward from a prior run (see
    workbook_state.py).
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
        ws.cell(row=r, column=COL_GUESTS, value=row.guest_count)
        ws.cell(row=r, column=COL_STAY_PATTERN, value=row.stay_pattern)
        ws.cell(row=r, column=COL_ONE_NIGHT_STAY, value="Yes" if row.one_night_stay else None)
        _write_date(ws, r, 10, row.booked_date)
        ws.cell(row=r, column=11, value=row.booking_window_days)
        ws.cell(row=r, column=12, value=row.bw_vs_median)
        ws.cell(row=r, column=13, value=row.my_adr)
        ws.cell(row=r, column=14, value=row.my_revenue)
        ws.cell(row=r, column=15, value=row.source)
        ws.cell(row=r, column=COL_TARGET_ADR, value=row.target_adr_p75)
        ws.cell(row=r, column=COL_VS_TARGET_DOLLAR, value=row.vs_target_dollar)
        ws.cell(row=r, column=COL_VS_TARGET_PCT, value=row.vs_target_pct)
        ws.cell(row=r, column=COL_MY_SEASON_ADR, value=row.my_season_adr)
        ws.cell(row=r, column=COL_VS_MY_SEASON_PCT, value=row.vs_my_season_pct)
        ws.cell(row=r, column=COL_MARKET_P25, value=row.market_p25)
        ws.cell(row=r, column=COL_MARKET_P90, value=row.market_p90)
        ws.cell(row=r, column=23, value=row.stly_adr)
        ws.cell(row=r, column=24, value=row.ly_occ)
        ws.cell(row=r, column=25, value=row.demand_tier)
        ws.cell(row=r, column=26, value=row.gap_before_days)
        ws.cell(row=r, column=COL_GAP_BEFORE_SIGNAL, value=row.gap_before_signal)
        ws.cell(row=r, column=28, value=row.gap_after_days)
        ws.cell(row=r, column=COL_GAP_AFTER_SIGNAL, value=row.gap_after_signal)
        ws.cell(row=r, column=STATUS_COL, value=row.status)
        ws.cell(row=r, column=RESERVATION_ID_COL, value=row.reservation_id)
        ws.cell(row=r, column=COL_OVERRIDE_NOTES, value=row.override_notes)

        saved = manual_notes.get(row.reservation_id)
        for offset in range(MANUAL_COLS_COUNT):
            value = saved[offset] if saved else None
            col = MANUAL_COLS_START + offset
            ws.cell(row=r, column=col, value=value)
            if col in MANUAL_PERCENT_SUFFIX_COLS:
                ws.cell(row=r, column=col).number_format = '0.0"%"'

        for col in MONEY_COLS:
            cell = ws.cell(row=r, column=col)
            if cell.value not in (None, "", "n/a"):
                cell.number_format = '$#,##0.00;("$"#,##0.00);\\-'
        for col in PCT_COLS:
            cell = ws.cell(row=r, column=col)
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0.0%"

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

        # Dropdown data validation for every "dropdown"-kind manual field --
        # a click instead of typing, and it keeps values consistent enough
        # to pivot/filter once there are enough rows to look for patterns.
        for i, (_name, kind, options) in enumerate(MANUAL_FIELDS):
            if kind != "dropdown":
                continue
            col = MANUAL_COLS_START + i
            dv = DataValidation(
                type="list",
                formula1='"' + ",".join(options) + '"',
                allow_blank=True,
                showDropDown=False,  # openpyxl quirk: False is what actually shows the arrow
            )
            ws.add_data_validation(dv)
            dv.add(col_range(col))

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
    ("My Season ADR (band)", True),
    (
        "This property's OWN historical ADR for the same calendar month and day-category "
        "(weekend-anchored vs. midweek), pooled across every year of history available. "
        "This exists because a comp set can be too flat to lean on alone (e.g. a comp "
        "that's just $300 weekday / $350 weekend year-round with no real seasonality of "
        "its own) -- when Target ADR (P75) and My Season ADR disagree, that disagreement "
        "is itself worth noticing. Shows 'not enough data' until this property has at "
        "least 3 historical nights in that same month + day-category.",
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
    ("Guests", True),
    ("Party size for the booking, straight from PriceLabs -- useful context alongside Nights/ADR (a 12-guest booking and a 2-guest booking at the same ADR aren't really comparable).", False),
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
    ("Override Notes (PriceLabs)", True),
    (
        "The `reason` text from any active PriceLabs date override on this booking's "
        "stay dates -- the same dated notes you already type by hand when pushing a "
        "pacing/LY-driven override (e.g. '9/12 - Pacing behind by -15.79%'). Pulled in "
        "automatically as context; blank if no override with a reason covers these dates.",
        False,
    ),
    ("", False),
    ("ADR vs Comp Rating", True),
    (
        "Compares your ADR to what you found searching Airbnb.com for the same dates (the "
        "Comp Check note) -- a snapshot against competitors, nothing to do with demand. "
        "Above/At/Below Comp are self-explanatory. 'Comp Has No Real Strategy' is for when "
        "the comps you found don't really vary by season (e.g. always ~$300 weekday / "
        "$350 weekend year-round) -- when that's the case, this rating alone won't tell "
        "you much; lean on Demand-ADR Fit and My Season ADR instead, since they compare "
        "you to demand and to your OWN history rather than to a comp set with no strategy "
        "of its own.",
        False,
    ),
    ("", False),
    ("Demand-ADR Fit", True),
    (
        "A DIFFERENT comparison from ADR vs Comp Rating: this one checks your ADR against "
        "the demand signal (Demand Tier / LY occ.), not against competitors. Great = a "
        "premium ADR on a High-demand date, or a defensibly lower ADR on a Low-demand "
        "date. Underpriced = High demand but you charged less than you could have -- "
        "money left on the table. Overpriced = your ADR was higher than what the demand "
        "level alone would suggest. Overpriced does NOT mean 'bad' or 'above comp' -- it's "
        "a purely demand-relative call. A booking can be Overpriced-for-demand and still "
        "be a Verdict = Win; that exact combination (rate the demand said should be low, "
        "priced high anyway, and someone paid it) is itself a real finding worth testing "
        "again on similar low-demand dates, not a contradiction to fix.",
        False,
    ),
    ("", False),
    ("Primary Lever", True),
    (
        "What actually got THIS booking to happen -- not whether it was a good outcome "
        "(that's Verdict, a separate question). Price = booked at your standard/listed "
        "rate, nothing special active. Min Stay = a minimum-stay REQUIREMENT you had in "
        "place shaped this booking's length (e.g. you required 2+ nights on that weekend, "
        "and that's structurally why it's exactly 2 nights, not more) -- not just 'this "
        "stay happened to be short.' LOS Discount = one of your Airbnb LOS Rule discounts "
        "was active and plausibly mattered. Pacing Push = an active pacing push (see "
        "Pacing Push %) is the likely reason. Organic-Unclear = nothing specific stands "
        "out -- no meaningful discount or push was active, the guest just booked at your "
        "posted price. When you're unsure between Price and Organic-Unclear, either is "
        "fine to pick -- the distinction that actually matters for finding patterns later "
        "is whether an LOS Discount or Pacing Push was active, or not.",
        False,
    ),
    ("", False),
    ("Manual review columns", True),
    (
        "Comp Check (Airbnb), Final PL Check, and Lesson Learned are free-typed. "
        "ADR vs Comp Rating, Demand-ADR Fit, Airbnb LOS Rule, LOS / Window Fit, Primary "
        "Lever, and Verdict are dropdowns (click, don't type) -- kept as short, "
        "consistent categories on purpose, since a countable rating is what turns into a "
        "real clue once you have 30-50 rows (e.g. 'Primary Lever = LOS Discount' + "
        "'Verdict = Win' happening 8 times in Low demand tells you something concrete). "
        "LOS Discount % (blended) and Pacing Push % are typed numbers. Every one of "
        "these is matched to each row by a hidden Reservation ID column, so a refresh "
        "never wipes out what you've typed -- it carries every column forward for any "
        "booking still in view, including one that's since been cancelled.",
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
