from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.hydrotest import HydrotestStatus
from app.utils.date_utils import check_due_after_test


class AssetCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "assetId": "GJ01AB9999",
                "station": "Demo Station A",
                "assetType": "Tanker Truck",
                "serialNumber": "DEMO-TT-099",
                "testDate": "2026-01-15",
                "nextDueDate": "2027-01-15",
            }
        },
    )

    assetId: str = Field(min_length=1, max_length=50)
    station: str = Field(min_length=1, max_length=100)
    assetType: str = Field(min_length=1, max_length=50)
    serialNumber: str = Field(min_length=1, max_length=50)
    testDate: date | None = None
    nextDueDate: date | None = None

    @model_validator(mode="after")
    def dates_in_order(self):
        check_due_after_test(self.testDate, self.nextDueDate)
        return self


class AssetUpdate(BaseModel):
    """PATCH body. assetId cannot be changed once the asset exists."""

    model_config = ConfigDict(str_strip_whitespace=True)

    station: str | None = Field(default=None, min_length=1, max_length=100)
    assetType: str | None = Field(default=None, min_length=1, max_length=50)
    serialNumber: str | None = Field(default=None, min_length=1, max_length=50)
    testDate: date | None = None
    nextDueDate: date | None = None

    @model_validator(mode="after")
    def dates_in_order(self):
        check_due_after_test(self.testDate, self.nextDueDate)
        return self


class AssetOut(BaseModel):
    id: str
    assetId: str
    station: str
    assetType: str
    serialNumber: str
    testDate: date | None
    nextDueDate: date | None
    status: HydrotestStatus
    createdAt: datetime
    updatedAt: datetime


class AssetOptions(BaseModel):
    stations: list[str]
    assetTypes: list[str]
