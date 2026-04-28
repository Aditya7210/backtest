from __future__ import annotations

from LiveMarket.calculations.calculation_runner import start_loop


def main() -> int:
    start_loop(interval_seconds=60.0)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
