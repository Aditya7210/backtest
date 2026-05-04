"""Repository for strategy file metadata."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

IMMUTABLE_STRATEGY_IDS = {
    "Tutorial_Backtrader_Strategies.py",
}


def _normalized_rel(path: Path) -> str:
    return str(path).replace("\\", "/")


def _is_immutable_relative(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return normalized in IMMUTABLE_STRATEGY_IDS


def is_immutable_strategy(*, strategy_id: str | None = None, path: Path | None = None) -> bool:
    if strategy_id:
        return _is_immutable_relative(strategy_id)
    if path is not None:
        try:
            rel = _normalized_rel(path.relative_to(get_strategies_dir()))
        except Exception:
            return False
        return _is_immutable_relative(rel)
    return False


def _find_project_root() -> Path:
    """Resolve project root by walking upward until Strategies/Strategy_codes exists.

    Falls back to expected repo layout relative to this file for first-run scenarios.
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "Strategies" / "Strategy_codes"
        if candidate.is_dir():
            return parent
    # backend/database/repositories -> backend -> repo root
    return here.parents[3]


def get_strategies_dir() -> Path:
    """Return strategy directory path."""
    return _find_project_root() / "Strategies" / "Strategy_codes"


def _safe_relative_path(strategy_id: str) -> Path | None:
    try:
        rel = Path(strategy_id)
    except Exception:
        return None
    if rel.is_absolute():
        return None
    if any(part in ("..", "") for part in rel.parts):
        return None
    if rel.suffix.lower() != ".py":
        return None
    return rel


def get_strategy_path_by_id(strategy_id: str) -> Path | None:
    rel = _safe_relative_path(strategy_id)
    if rel is None:
        return None
    candidate = (get_strategies_dir() / rel).resolve()
    base = get_strategies_dir().resolve()
    if base not in candidate.parents and candidate != base:
        return None
    if candidate.is_file():
        return candidate
    return None


def get_strategy_path(name: str) -> Path | None:
    """Resolve safe strategy file path; returns None for invalid names."""
    safe_name = Path(name).name
    if "/" in name or "\\" in name or ".." in name:
        return None
    strategies_dir = get_strategies_dir()
    direct = strategies_dir / f"{safe_name}.py"
    if direct.is_file():
        return direct

    matches = [p for p in strategies_dir.rglob("*.py") if p.stem == safe_name and "__pycache__" not in p.parts]
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_strategy_path(strategy_id: str | None = None, name: str | None = None) -> Path | None:
    """Resolve by stable relative_path first, then by legacy stem name."""
    if strategy_id:
        by_id = get_strategy_path_by_id(strategy_id)
        if by_id is not None:
            return by_id
    if name:
        return get_strategy_path(name)
    return None


def list_strategies() -> list[dict[str, Any]]:
    """List all strategy Python files."""
    strategies_dir = get_strategies_dir()
    if not strategies_dir.is_dir():
        return []
    strategies = []
    for f in sorted(strategies_dir.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(strategies_dir)
        relative_path = _normalized_rel(rel)
        strategies.append({
            "name": f.stem,
            "filename": f.name,
            "relative_path": relative_path,
            "size_bytes": f.stat().st_size,
            "immutable": _is_immutable_relative(relative_path),
        })
    return strategies


def get_source(name: str | None = None, strategy_id: str | None = None) -> str | None:
    """Get strategy source by stable id or legacy name."""
    path = resolve_strategy_path(strategy_id=strategy_id, name=name)
    if path is None:
        return None
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def save_source(
    name: str,
    source: str,
    *,
    strategy_id: str | None = None,
    versioning_enabled: bool = False,
) -> tuple[bool, str | None]:
    """Save strategy source code and return saved strategy_id."""
    safe_name = Path(name).name
    if "/" in safe_name or "\\" in safe_name or ".." in safe_name:
        return False, None
    if not safe_name.strip():
        return False, None
    if not re.fullmatch(r"[A-Za-z0-9 _-]+", safe_name):
        return False, None

    base_dir = get_strategies_dir()
    target: Path | None = None
    original_path: Path | None = None

    if versioning_enabled:
        version_root = base_dir / "strategy_versioning"
        version_root.mkdir(parents=True, exist_ok=True)
        stem = safe_name.removesuffix(".py")
        if stem.endswith(".py"):
            stem = stem[:-3]
        pattern = f"{stem}_v*.py"
        max_version = 0
        for existing in version_root.glob(pattern):
            suffix = existing.stem.replace(f"{stem}_v", "", 1)
            if suffix.isdigit():
                max_version = max(max_version, int(suffix))
        target = version_root / f"{stem}_v{max_version + 1}.py"
    else:
        if strategy_id:
            path_by_id = get_strategy_path_by_id(strategy_id)
            if path_by_id is not None:
                if is_immutable_strategy(path=path_by_id):
                    return False, None
                original_path = path_by_id
                desired = path_by_id.with_name(f"{safe_name}.py")
                desired_resolved = desired.resolve()
                base_resolved = base_dir.resolve()
                if base_resolved not in desired_resolved.parents:
                    return False, None
                # Rename intent when user changed save name.
                if desired != path_by_id:
                    if desired.exists() and desired != path_by_id:
                        return False, None
                    target = desired
                else:
                    target = path_by_id
        if target is None:
            target = base_dir / f"{safe_name}.py"
            if target.exists() and strategy_id is None:
                return False, None

    target_rel = _normalized_rel(target.relative_to(base_dir))
    if _is_immutable_relative(target_rel):
        return False, None

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    if original_path is not None and original_path != target and original_path.exists():
        original_path.unlink()
    saved_id = str(target.relative_to(base_dir)).replace("\\", "/")
    return True, saved_id


def list_strategy_classes(name: str | None = None, strategy_id: str | None = None) -> list[str]:
    """List candidate strategy classes in a strategy file."""
    source = get_source(name=name, strategy_id=strategy_id)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    classes: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        base_names: list[str] = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(base.attr)

        if any(name.endswith("Strategy") for name in base_names):
            classes.append(node.name)
            continue

        # Keep compatibility with files that define single top-level classes.
        if node.name.endswith("Strategy"):
            classes.append(node.name)

    return sorted(set(classes))
