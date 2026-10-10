from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import FileResponse

from app import config
from app.database.connection import get_db
from app.errors import BadRequest
from app.schemas.inspection import FrameScanOut, InspectionOut, PlateCorrection, PlateLookup, ProcessRequest
from app.services import inspection_service

router = APIRouter(prefix="/api/inspection", tags=["Video inspection"])


@router.post("/upload-video", response_model=InspectionOut, status_code=201, summary="Upload an inspection video")
def upload_video(file: UploadFile = File(...), db=Depends(get_db)):
    """Accepts .mp4, .avi, .mov and .mkv. Returns an inspection id to process."""
    return inspection_service.save_upload(db, file)


@router.post("/process-video", response_model=InspectionOut, status_code=202, summary="Start plate detection on an uploaded video")
def process_video(body: ProcessRequest, background_tasks: BackgroundTasks, db=Depends(get_db)):
    """Returns straight away. Poll GET /results/{id} for progress and the final result."""
    inspection = inspection_service.prepare_processing(db, body.inspectionId)
    background_tasks.add_task(inspection_service.process_video, db, body.inspectionId)
    return inspection


@router.get("/results/{inspection_id}", response_model=InspectionOut, summary="Get progress / result of an inspection")
def get_result(inspection_id: str, db=Depends(get_db)):
    return inspection_service.get_result(db, inspection_id)


@router.patch("/results/{inspection_id}", response_model=InspectionOut, summary="Manually correct the detected number plate")
def correct_plate(inspection_id: str, body: PlateCorrection, db=Depends(get_db)):
    return inspection_service.correct_plate(db, inspection_id, body.plateNumber)


@router.get("/results/{inspection_id}/plate-image", summary="Cropped plate image")
def get_plate_image(inspection_id: str, db=Depends(get_db)):
    return FileResponse(inspection_service.get_plate_image_path(db, inspection_id), media_type="image/jpeg")


@router.get("/assets/{plate_number}", response_model=PlateLookup, summary="Find an asset and its hydrotest status by plate number")
def lookup_plate(plate_number: str, db=Depends(get_db)):
    """Not finding an asset is not an error: the response has found=false and status NOT_FOUND."""
    return inspection_service.lookup_plate(db, plate_number)

IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "application/octet-stream")


@router.post("/scan-frame", response_model=FrameScanOut, summary="Live camera frame -> plate -> OCR -> hydrotest status")
def scan_frame(save: bool = False, file: UploadFile = File(...), db=Depends(get_db)):
    if file.content_type and file.content_type.lower() not in IMAGE_TYPES:
        raise BadRequest("Please send a JPG, PNG or WebP image.")
    limit = config.MAX_IMAGE_MB * 1024 * 1024
    data = file.file.read(limit + 1)
    if not data:
        raise BadRequest("The image is empty.")
    if len(data) > limit:
        raise BadRequest(f"The image is too large. The maximum size is {config.MAX_IMAGE_MB} MB.")
    return inspection_service.scan_frame(db, data, save)


@router.post("/detect-plate", summary="Live camera: is the whole number plate in view, big and sharp enough?")
def detect_plate(full_width: int | None = None, file: UploadFile = File(...)):
    """Quick YOLO-only check (no OCR). The camera sends a small frame several times a second and takes
    the full-size photo only when `ready` is true."""
    data = file.file.read(5 * 1024 * 1024 + 1)
    if not data:
        raise BadRequest("The image is empty.")
    if len(data) > 5 * 1024 * 1024:
        raise BadRequest("The preview frame is too large.")
    return inspection_service.detect_plate_quick(data, full_width)