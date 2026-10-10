from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.asset import AssetOut
from app.schemas.hydrotest import HydrotestOut
from app.models.hydrotest import HydrotestStatus


class ProcessRequest(BaseModel):
    inspectionId: str


class PlateCorrection(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    plateNumber: str = Field(min_length=3, max_length=30)


class PlateLookup(BaseModel):
    plateNumber: str
    found: bool
    hydrotestStatus: HydrotestStatus
    asset: AssetOut | None = None
    latestHydrotest: HydrotestOut | None = None


class InspectionOut(BaseModel):
    id: str
    videoName: str
    status: str
    progress: int
    detectedPlate: str | None
    rawText: str | None
    confidence: float | None
    detectionConfidence: float | None
    lowConfidence: bool
    manuallyCorrected: bool
    hasPlateImage: bool
    assetId: str | None
    hydrotestStatus: str | None
    message: str | None
    createdAt: datetime
    updatedAt: datetime
    lookup: PlateLookup | None = None

class FrameScanOut(BaseModel):
    plateDetected: bool
    plateNumber: str | None = None
    ocrConfidence: float | None = None
    detectionConfidence: float | None = None
    lowConfidence: bool = False
    plateFormatValid: bool = False
    message: str | None = None
    inspection: InspectionOut | None = None  # only filled when save=true
