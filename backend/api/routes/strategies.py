"""Strategy management REST routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database.repositories import strategy_repository

router = APIRouter(tags=["strategies"])


class StrategySaveRequest(BaseModel):
    name: str
    source: str
    strategy_id: str | None = None
    versioning_enabled: bool = False


@router.get("/strategies")
def list_strategies():
    """List available strategy files."""
    return {"strategies": strategy_repository.list_strategies()}


@router.get("/strategies/source")
def get_strategy_source(
    strategy_id: str | None = Query(default=None),
    name: str | None = Query(default=None),
):
    """Get strategy source code by stable id or legacy name."""
    source = strategy_repository.get_source(name=name, strategy_id=strategy_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"name": name or "", "strategy_id": strategy_id, "source": source}


@router.get("/strategies/classes")
def get_strategy_classes(
    strategy_id: str | None = Query(default=None),
    name: str | None = Query(default=None),
):
    """List strategy class names by stable id or legacy name."""
    source = strategy_repository.get_source(name=name, strategy_id=strategy_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {
        "name": name or "",
        "strategy_id": strategy_id,
        "classes": strategy_repository.list_strategy_classes(name=name, strategy_id=strategy_id),
    }


@router.get("/strategies/{name}")
def get_strategy_source_legacy(name: str):
    """Legacy source endpoint preserved for compatibility."""
    return get_strategy_source(name=name)


@router.get("/strategies/{name}/classes")
def get_strategy_classes_legacy(name: str):
    """Legacy classes endpoint preserved for compatibility."""
    return get_strategy_classes(name=name)


@router.post("/strategies")
def save_strategy(request: StrategySaveRequest):
    """Save or update a strategy."""
    safe_name = request.name.strip().replace("\\", "/").split("/")[-1]
    target_id = f"{safe_name.removesuffix('.py')}.py"
    if strategy_repository.is_immutable_strategy(strategy_id=request.strategy_id) or strategy_repository.is_immutable_strategy(strategy_id=target_id):
        raise HTTPException(status_code=403, detail="This strategy file is immutable and cannot be modified.")
    ok, saved_id = strategy_repository.save_source(
        request.name,
        request.source,
        strategy_id=request.strategy_id,
        versioning_enabled=request.versioning_enabled,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid strategy payload")
    return {"status": "saved", "name": request.name, "strategy_id": saved_id}
