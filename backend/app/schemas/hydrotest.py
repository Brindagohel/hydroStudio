import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.hydrotest import HydrotestStatus, TestResult
from app.schemas.asset import AssetOut
from app.utils.date_utils import check_due_after_test

# only a plain file name, never a path
REPORT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,99}$")


def _check_report_name(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if ".." in value or not REPORT_NAME.match(value):
        raise ValueError("Report file must be a simple file name like demo-report-001.pdf")
    return value


class HydrotestCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "assetId": "GJ01AB1234",
                "testDate": "2026-03-10",
                "performedBy": "Demo Inspector",
                "result": "Pass",
                "notes": "Held pressure for 30 minutes",
                "reportFile": "demo-report-020.pdf",
                "nextDueDate": "2027-03-10",
            }
        },
    )

    assetId: str = Field(min_length=1, max_length=50)
    testDate: date
    performedBy: str = Field(min_length=1, max_length=100)
    result: TestResult
    notes: str = Field(default="", max_length=1000)
    reportFile: str | None = None
    nextDueDate: date | None = None

    @field_validator("reportFile")
    @classmethod
    def report_file_is_safe(cls, value):
        return _check_report_name(value)

    @model_validator(mode="after")
    def dates_in_order(self):
        check_due_after_test(self.testDate, self.nextDueDate)
        return self


class HydrotestUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    testDate: date | None = None
    performedBy: str | None = Field(default=None, min_length=1, max_length=100)
    result: TestResult | None = None
    notes: str | None = Field(default=None, max_length=1000)
    reportFile: str | None = None
    nextDueDate: date | None = None

    @field_validator("reportFile")
    @classmethod
    def report_file_is_safe(cls, value):
        return _check_report_name(value)

    @model_validator(mode="after")
    def dates_in_order(self):
        check_due_after_test(self.testDate, self.nextDueDate)
        return self


class HydrotestOut(BaseModel):
    id: str
    assetId: str
    testDate: date
    nextDueDate: date | None
    performedBy: str
    result: TestResult
    notes: str
    reportFile: str | None
    createdAt: datetime
    updatedAt: datetime


class SummaryOut(BaseModel):
    totalAssets: int
    valid: int
    dueSoon: int
    overdue: int
    failed: int
    pending: int
    needsAttention: list[AssetOut]
    recentRecords: list[HydrotestOut]


class LatestStatusOut(BaseModel):
    assetId: str
    status: HydrotestStatus
