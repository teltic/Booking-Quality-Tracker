"""Convenience entrypoint: `python run.py` from the repo root.

Exists so you don't have to set PYTHONPATH or remember the `-m` package
form -- `booking_quality_log` lives under `src/`, which Python doesn't add
to its import path automatically.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from booking_quality_log.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
