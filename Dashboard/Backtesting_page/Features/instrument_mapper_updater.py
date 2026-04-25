from __future__ import annotations

import os

from instrument_mapper import InstrumentMapper


def main() -> None:
    api_key = (os.getenv("ZERODHA_API_KEY") or "").strip()
    access_token = (os.getenv("ZERODHA_ACCESS_TOKEN") or "").strip()

    if not api_key or not access_token:
        print(
            "Instrument mapper updater skipped: missing ZERODHA_API_KEY or ZERODHA_ACCESS_TOKEN."
        )
        return

    try:
        mapper = InstrumentMapper(
            api_key=api_key,
            access_token=access_token,
            auto_update=False,
        )
        mapper.update_instruments()
        print("Instrument mapper update completed.")
    except Exception as exc:
        print(f"Instrument mapper update failed: {exc}")


if __name__ == "__main__":
    main()
