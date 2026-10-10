from fastapi import APIRouter, Depends

from app.database.connection import get_db
from app.schemas.hydrotest import SummaryOut
from app.services import asset_service

router = APIRouter(prefix="/api/hydrotests", tags=["Dashboard"])


@router.get("/summary", response_model=SummaryOut, summary="Dashboard numbers and due/overdue records")
def get_summary(db=Depends(get_db)):
    return asset_service.get_summary(db)
