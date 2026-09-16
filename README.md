# Booking-Quality-Tracker

Generates the **Booking Quality Log** workbook: one row per confirmed (or
since-cancelled) booking across your properties, flagging upsell/discount
gap opportunities, below-target pricing, and other booking-quality
signals. Pulls live data from PriceLabs' API; only writes a new file on a
day at least one brand-new confirmed booking shows up, so it's safe to run
on an unattended daily schedule.

This started as a hand-refreshed spreadsheet built inside a Claude chat,
then got automated. It lives in its own repo, separate from any other
Airbnb/PriceLabs tooling you may have, so each tool can be set up, run,
and scheduled independently.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in PRICELABS_API_KEY
```

Get your API key from the PriceLabs dashboard: Account Settings > API.

Edit `config/listings.yaml` to add/remove properties (PMS name + listing
ID for each).

**Where output gets saved is set separately, not in `.env`.** `.env` only
ever holds `PRICELABS_API_KEY`. The output folder is the `OUTPUT_DIR` line
near the top of `run_daily.bat` -- edit that file directly if you want to
change it (see Usage below).

## Usage

### One-click / daily automated (Windows)

- **`run_daily.bat`** -- double-click to check PriceLabs for brand-new
  confirmed bookings and, if there are any, write today's dated workbook
  (`Booking Quality Log - YYYY-MM-DD.xlsx`) into the folder set as
  `OUTPUT_DIR` at the top of that file. If nothing new booked since the
  last file it wrote (even if that was several days ago), it skips
  writing anything and exits quietly -- that's expected, not a failure.
- **`setup_daily_task.bat`** -- run once to register a Windows Scheduled
  Task that runs `run_daily.bat` automatically every day (default 7:00 AM
  -- edit `RUN_TIME` at the top of the file, then rerun it, to change
  that). Safe to rerun any time to update the schedule.

### Manual / command line

```
python run.py --output-dir output
```

Useful flags:

- `--output-dir DIR` -- folder to write today's dated workbook into (and
  read the most recent prior one from, to check for new bookings and
  carry manual notes forward). Defaults to `output/` in the repo.
- `--force` -- write today's file even if no new confirmed booking was
  found (useful for testing, or to pick up a change you made by hand to
  the pulled data).
- `--listings-config PATH` -- use a listings file other than
  `config/listings.yaml`.

## How this works

One workbook, two tabs ("Read Me" + "Booking Quality Log"), covering all
configured properties combined -- one row per booking with check-in on or
after **2026-09-01** (a fixed cutoff, by explicit request -- not a rolling
"today onward" window, so it won't silently start showing fewer rows as
time passes), sorted by **Booked date, newest first** (not by check-in).

Each row carries:

- **Nights / Stay Pattern / 1-Night Stay** -- "Weekend-anchored" if the
  stay includes a Friday or Saturday night, else "Midweek"; 1-Night Stay
  flags a single-night booking regardless of anything else.
- **Booking Window / BW vs Median** -- lead time (booked date to
  check-in) vs. that property's own median lead time across all its
  bookings. "Far out" = booked well ahead of typical; "Last-minute" =
  well after typical.
- **Target ADR (P75) / vs Target ($, %)** -- both properties are set to
  Premium tier, so the benchmark is the comp set's 75th-percentile price
  for the stay dates, not the median. Blank/"n/a" when PriceLabs has no
  comp-set data for those dates.
- **My Season ADR (band) / vs My Season (%)** -- this property's OWN
  historical ADR for the same calendar month + day-category (weekend vs.
  midweek), pooled across every year of history available (excluding this
  booking's own night, so it never skews its own benchmark). Exists
  because a comp set can be too flat to lean on alone (e.g. one that's
  just $300 weekday / $350 weekend year-round, with no real seasonality
  of its own) -- when this and Target ADR (P75) disagree, that
  disagreement is itself worth noticing. "not enough data" until this
  property has 3+ historical nights in that same month + day-category.
- **Market P25 / P90** -- extra context on how wide the comp set's
  pricing spread is on those dates.
- **STLY ADR** -- your own actual ADR from the same calendar dates last
  year, where a booking existed then. Coverage is thin by nature (depends
  on having had a booking on that exact date a year ago).
- **LY occ. (per night)** -- comp-set market occupancy on the same
  calendar dates last year, shown one value per night of the stay (e.g.
  "20%, 65%" for a 2-night stay) rather than averaged, so a night that
  historically struggles to fill doesn't get smoothed away by a strong
  neighboring night.
- **Demand Tier** -- comp-set market occupancy on the stay dates,
  bucketed Low (<30%), Mid (30-60%), High (60%+).
- **Gap Before / After (d) + Signal** -- nights of vacancy between this
  booking and the adjacent confirmed one on that property's calendar.
  1-night gap = "Upsell candidate"; 2-night gap = "LOS-discount
  candidate", each noting how often comp-set occupancy suggests that gap
  fills on its own. A booking at the edge of the pulled data window gets
  a text note ("first/last known booking in window") instead of a
  numeric gap.
- **Status** -- Confirmed or Cancelled. A cancelled booking stays on the
  log (grayed out) instead of disappearing, so a note already typed on it
  isn't lost. Gap Before/After don't apply to a cancelled booking (it no
  longer holds calendar space), so those show "n/a (cancelled)". A
  cancellation by itself never triggers a new file being written -- only
  a brand-new confirmed booking does.
- **Override Notes (PriceLabs)** -- the `reason` text from any PriceLabs
  date override covering this booking's stay dates -- the same dated
  notes you already type by hand when pushing a pacing/LY-driven override
  (e.g. "9/12 - Pacing behind by -15.79%"). Pulled in automatically as
  context; blank if nothing with a reason covers these dates.

Full plain-language descriptions are also in the workbook's own "Read Me"
tab, which travels with every file you generate.

### The manual review block never gets erased

Eleven columns, all matched to each row by a hidden **Reservation ID**
column (PriceLabs' own channel confirmation code, e.g. an Airbnb code
like `HMT5EBPQ54`), so whenever a new file is written, everything you
typed or picked on a booking that's still in view -- including one that's
since been cancelled -- is carried forward from the most recent prior
file automatically. This lookup is done by each column's header text at
read time (not a fixed column position), so it also survives a future
column being added or a manual column being renamed.

Built for pattern-finding once there are 30-50+ rows, not just per-booking
notes -- most of these are short **dropdowns** (a click, not typing) so
they stay consistent enough to filter/pivot on, e.g. "how often did
Primary Lever = LOS Discount coincide with Verdict = Win in Low demand
months":

| Column | Type | Notes |
|---|---|---|
| Comp Check (Airbnb) | free text | what you saw on a manual Airbnb.com search |
| ADR vs Comp Rating | dropdown | Above Comp / At Comp / Below Comp / Comp Has No Real Strategy |
| Demand-ADR Fit | dropdown | Great / OK / Underpriced / Overpriced -- given LY occ./Demand Tier, was the ADR right? |
| Airbnb LOS Rule | dropdown | which of your named PriceLabs LOS discount rule sets was active (can't be auto-detected -- PriceLabs' API exposes none of seasonality/day-of-week/overrides/rate-plans by a rule-set name, checked live) |
| LOS / Window Fit | dropdown | Ideal / Acceptable / Suboptimal -- did lead time and length of stay make sense together for the season? |
| LOS Discount % (blended) | number | your own manual, revenue-weighted blend across the stay's nights (e.g. a 4-night stay with 1 night at 35% off blends to ~9%, not 35%) |
| Primary Lever | dropdown | Price / Min Stay / LOS Discount / Pacing Push / Organic-Unclear -- what actually got this booked? |
| Pacing Push % | number | the push % active when it booked |
| Final PL Check | free text | your LY/2LY gut-check comparison |
| Verdict | dropdown | Win / Loss / Neutral / Too Early to Tell |
| Lesson Learned | free text | what this specific booking taught you |

## Known limitations / assumptions worth knowing before you trust this

1. **PriceLabs API endpoints are the same ones verified live for the
   sibling pricing tool** (`neighborhood_data`, `overrides`,
   `reservation_data`), via the same request shapes. `get_listings` is
   unverified; if it ever 404s, `PriceLabsAPIError` prints the failing URL
   and response body, and a wrong path is a one-line fix in the
   `ENDPOINTS` dict in `pricelabs_client.py`.

2. **A comp-set split into multiple bedroom-count segments uses the
   largest one for percentiles.** Some listings' comp-set data comes back
   as several sub-groups (one per bedroom count) instead of one blended
   group -- this tool picks the sub-group with the most listings for
   Target ADR/Market P25/P90/Demand Tier, to avoid a tiny sub-group making
   every percentile identical.

3. **Blended ADR, not per-night.** My ADR/Revenue and STLY ADR all come
   from stay-level (not true per-night) reservation data -- a multi-night
   reservation's average rate is treated as that rate for every night in
   the stay.

4. **Fixed date filter, not rolling.** The 2026-09-01 cutoff is a fixed
   date by explicit request, not "today onward" -- it won't silently
   start showing fewer/no rows as time passes, but it also won't move on
   its own; update `START_DATE` in `src/booking_quality_log/compute.py`
   if you want it to roll forward instead.

5. **No automatic PriceLabs changes.** This tool only reports what it
   finds -- it never writes back to PriceLabs (no price/min-stay
   overrides). Any action based on what it flags is yours to take by hand.

## Project layout

```
run.py                      # double-click-equivalent CLI entrypoint
run_daily.bat                # double-click to check for new bookings / generate today's workbook
setup_daily_task.bat         # run once to schedule run_daily.bat daily
config/listings.yaml         # properties to process (name, PMS, listing ID)
src/booking_quality_log/
  pricelabs_client.py         # REST API wrapper
  market.py                   # neighborhood/comp-set data parser
  reservations.py              # reservation fetch/parse
  compute.py                   # gap/target-ADR/demand-tier/BW-median/STLY row-building logic
  workbook_build.py            # openpyxl workbook construction (Read Me + Booking Quality Log tabs)
  workbook_state.py            # read-back of Reservation IDs + manual notes for reruns and the skip check
  dated_output.py              # daily-snapshot filename/most-recent-prior-file lookup
  main.py                      # CLI entrypoint, including the new-booking skip check
tests/                        # unit tests (no network required)
```

Run tests with `python -m pytest tests/`.
