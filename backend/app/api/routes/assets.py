from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.database.connection import get_db
from app.models.hydrotest import HydrotestStatus
from app.schemas.asset import AssetCreate, AssetOptions, AssetOut, AssetUpdate
from app.services import asset_service

router = APIRouter(prefix="/api/hydrotests/assets", tags=["Assets"])


@router.post("", response_model=AssetOut, status_code=201, summary="Create an asset")
def create_asset(data: AssetCreate, db=Depends(get_db)):
    """Returns 409 if the asset ID or serial number already exists."""
    return asset_service.create_asset(db, data)


@router.get("", response_model=list[AssetOut], summary="List assets with filters, search and sorting")
def list_assets(
    station: str | None = None,
    asset_type: str | None = None,
    status: HydrotestStatus | None = None,
    due_from: date | None = Query(default=None, description="Next due date on or after this day"),
    due_to: date | None = Query(default=None, description="Next due date on or before this day"),
    search: str | None = Query(default=None, description="Matches asset ID, serial number, station or type"),
    sort_by: Literal["nextDueDate", "testDate", "assetId", "station"] = "nextDueDate",
    sort_order: Literal["asc", "desc"] = "asc",
    db=Depends(get_db),
):
    return asset_service.list_assets(db, station, asset_type, status, due_from, due_to, search, sort_by, sort_order)


@router.get("/options", response_model=AssetOptions, summary="Stations and asset types for filter drop-downs")
def get_options(db=Depends(get_db)):
    return asset_service.get_options(db)


@router.get("/{asset_id}", response_model=AssetOut, summary="Get one asset by asset ID")
def get_asset(asset_id: str, db=Depends(get_db)):
    return asset_service.get_asset(db, asset_id)


@router.patch("/{asset_id}", response_model=AssetOut, summary="Update an asset")
def update_asset(asset_id: str, data: AssetUpdate, db=Depends(get_db)):
    return asset_service.update_asset(db, asset_id, data)
