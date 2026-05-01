"""Calculator entry point — runnable as `python -m backend.calculations.run_calculator`."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    from backend.calculations.runner import start_loop
    start_loop(interval_seconds=10.0)


if __name__ == "__main__":
    main()
