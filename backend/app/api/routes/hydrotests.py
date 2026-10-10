from fastapi import APIRouter, Depends

from app.database.connection import get_db
from app.models.hydrotest import TestResult
from app.schemas.hydrotest import HydrotestCreate, HydrotestOut, HydrotestUpdate
from app.services import hydrotest_service

router = APIRouter(prefix="/api/hydrotests/records", tags=["Hydrotest records"])


@router.post("", response_model=HydrotestOut, status_code=201, summary="Create a hydrotest record")
def create_record(data: HydrotestCreate, db=Depends(get_db)):
    """The asset must already exist. The asset's test date, due date and status are refreshed."""
    return hydrotest_service.create_record(db, data)


@router.get("", response_model=list[HydrotestOut], summary="List hydrotest records, newest first")
def list_records(asset_id: str | None = None, result: TestResult | None = None, db=Depends(get_db)):
    return hydrotest_service.list_records(db, asset_id, result)


@router.get("/{record_id}", response_model=HydrotestOut, summary="Get one hydrotest record")
def get_record(record_id: str, db=Depends(get_db)):
    return hydrotest_service.get_record(db, record_id)


@router.patch("/{record_id}", response_model=HydrotestOut, summary="Update a hydrotest record")
def update_record(record_id: str, data: HydrotestUpdate, db=Depends(get_db)):
    return hydrotest_service.update_record(db, record_id, data)
