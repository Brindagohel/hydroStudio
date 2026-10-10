from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.cng import CngStatus
from app.utils.date_utils import check_due_after_test
from app.utils.plate_utils import normalize_plate


class CylinderTestCreate(BaseModel):
    """One hydrotest of one CNG cylinder fitted to a vehicle."""

    vehicleNumber: str = Field(min_length=4, max_length=20)
    cylinderSerial: str = Field(min_length=2, max_length=40)
    manufactureDate: date | None = None
    testDate: date
    nextDueDate: date | None = None  # if empty, testDate + CNG_TEST_VALIDITY_YEARS is used
    result: Literal["Pass", "Fail"]
    testCenter: str | None = Field(default=None, max_length=120)
    reportNumber: str | None = Field(default=None, max_length=60)

    @field_validator("vehicleNumber")
    @classmethod
    def clean_plate(cls, value):
        plate = normalize_plate(value)
        if len(plate) < 4:
            raise ValueError("Enter a valid vehicle registration number")
        return plate

    @field_validator("cylinderSerial")
    @classmethod
    def clean_serial(cls, value):
        value = value.strip().upper()
        if not value:
            raise ValueError("Cylinder serial number is required")
        return value

    @model_validator(mode="after")
    def check_dates(self):
        if self.testDate > date.today():
            raise ValueError("Test date cannot be in the future")
        if self.manufactureDate and self.manufactureDate > self.testDate:
            raise ValueError("Manufacture date cannot be after the test date")
        check_due_after_test(self.testDate, self.nextDueDate)
        return self


class CylinderTestOut(BaseModel):
    id: str
    vehicleNumber: str
    cylinderSerial: str
    manufactureDate: date | None
    testDate: date
    nextDueDate: date | None
    result: str
    testCenter: str | None
    reportNumber: str | None
    createdAt: datetime


class VehicleOut(BaseModel):
    registrationNumber: str
    fuelType: str | None
    ownerName: str | None  # masked, e.g. "D**** O***"
    vehicleClass: str | None
    makerModel: str | None
    registrationDate: str | None
    fitnessValidUpto: str | None
    source: str


class CylinderStatusOut(BaseModel):
    cylinderSerial: str
    manufactureDate: date | None
    lastTestDate: date
    nextDueDate: date
    daysToDue: int  # negative = days overdue
    result: str
    testCenter: str | None
    reportNumber: str | None
    status: CngStatus


class CngVerificationOut(BaseModel):
    plateNumber: str
    status: CngStatus
    message: str
    vehicle: VehicleOut | None
    cylinders: list[CylinderStatusOut]
    checkedAt: datetime


class CngScanOut(BaseModel):
    plateDetected: bool
    plateNumber: str | None = None
    ocrConfidence: float | None = None
    detectionConfidence: float | None = None
    lowConfidence: bool = False
    plateFormatValid: bool = False
    plateCorrectedFrom: str | None = None  # set when a look-alike fix (e.g. 0 -> O) matched a registered vehicle
    message: str | None = None
    verification: CngVerificationOut | None = None