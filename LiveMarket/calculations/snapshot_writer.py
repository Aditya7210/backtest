from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    temp_path.replace(path)


def write_all(
    snapshots_dir: Path,
    *,
    vwap_snapshot: dict[str, Any],
    ad_snapshot: dict[str, Any],
    pcr_snapshot: dict[str, Any],
    atm_oi_snapshot: dict[str, Any],
    vix_snapshot: dict[str, Any],
) -> None:
    _atomic_write_json(snapshots_dir / "vwap_snapshot.json", vwap_snapshot)
    _atomic_write_json(snapshots_dir / "ad_snapshot.json", ad_snapshot)
    _atomic_write_json(snapshots_dir / "pcr_snapshot.json", pcr_snapshot)
    _atomic_write_json(snapshots_dir / "atm_oi_snapshot.json", atm_oi_snapshot)
    _atomic_write_json(snapshots_dir / "vix_snapshot.json", vix_snapshot)


__all__ = ["write_all"]

