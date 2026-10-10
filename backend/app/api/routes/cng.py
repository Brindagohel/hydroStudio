from fastapi import APIRouter, Depends, File, UploadFile

from app import config
from app.database.connection import get_db
from app.errors import BadRequest
from app.schemas.cng import CngScanOut, CngVerificationOut, CylinderTestCreate, CylinderTestOut
from app.services import cng_service

router = APIRouter(prefix="/api/cng", tags=["CNG hydrotest verification"])

IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")


@router.get("/verify/{plate_number}", response_model=CngVerificationOut, summary="Verify CNG hydrotest for a vehicle number")
def verify_plate(plate_number: str, db=Depends(get_db)):
    """Fetches vehicle details from the configured provider, then checks the cylinder hydrotest records."""
    return cng_service.verify(db, plate_number)


@router.post("/scan", response_model=CngScanOut, summary="Camera snapshot or photo -> plate -> CNG verification")
def scan(file: UploadFile = File(...), db=Depends(get_db)):
    """Send one image (the browser camera sends a JPEG frame). No plate in the image is a normal answer
    (`plateDetected=false`), not an error, so the camera can keep trying."""
    if file.content_type and file.content_type.lower() not in IMAGE_TYPES + ("application/octet-stream",):
        raise BadRequest("Please send a JPG, PNG or WebP image.")
    limit = config.MAX_IMAGE_MB * 1024 * 1024
    data = file.file.read(limit + 1)
    if not data:
        raise BadRequest("The image is empty.")
    if len(data) > limit:
        raise BadRequest(f"The image is too large. The maximum size is {config.MAX_IMAGE_MB} MB.")
    return cng_service.scan_image(db, data)


@router.post("/cylinder-tests", response_model=CylinderTestOut, status_code=201, summary="Add a CNG cylinder hydrotest record")
def create_cylinder_test(body: CylinderTestCreate, db=Depends(get_db)):
    return cng_service.create_test(db, body)


@router.get("/cylinder-tests", response_model=list[CylinderTestOut], summary="List cylinder hydrotest records")
def list_cylinder_tests(vehicle_number: str | None = None, db=Depends(get_db)):
    return cng_service.list_tests(db, vehicle_number)
