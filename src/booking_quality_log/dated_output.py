"""Dated daily-snapshot output: one file per day a new confirmed booking
was found, in a folder. Because a day with nothing new is skipped
entirely (no file written), "the most recent prior file" can be from any
number of days back, not just yesterday -- the glob below handles that
the same way regardless of how big the gap is.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

FILENAME_STEM = "Booking Quality Log"
_DATED_FILENAME_RE = re.compile(re.escape(FILENAME_STEM) + r" - (\d{4}-\d{2}-\d{2})\.xlsx$")


def dated_filename(date: dt.date) -> str:
    return f"{FILENAME_STEM} - {date.isoformat()}.xlsx"


def find_most_recent_prior_file(output_dir: Path, today: dt.date) -> Path | None:
    """The most recent dated file in `output_dir` dated today or earlier
    (never a future-dated file), or None if there isn't one yet (first-ever
    run). Preferring *today's own* file when one already exists (rather
    than always the latest strictly-earlier one) matters for a same-day
    rerun: if a new booking already triggered a write today and Thomas
    typed a manual note into that file, rerunning later the same day must
    read that note back rather than silently discarding it.
    """
    latest: tuple[dt.date, Path] | None = None
    if not output_dir.exists():
        return None
    for candidate in output_dir.glob(f"{FILENAME_STEM} - *.xlsx"):
        match = _DATED_FILENAME_RE.search(candidate.name)
        if not match:
            continue
        file_date = dt.date.fromisoformat(match.group(1))
        if file_date <= today and (latest is None or file_date > latest[0]):
            latest = (file_date, candidate)
    return latest[1] if latest else None
