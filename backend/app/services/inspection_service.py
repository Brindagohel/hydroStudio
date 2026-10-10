import logging
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import UploadFile

from app import config
from app.errors import AppError, BadRequest, NotFoundError
from app.models.hydrotest import record_to_dict
from app.models.asset import asset_to_dict
from app.models.inspection import InspectionStatus, inspection_to_dict
from app.services import asset_service, hydrotest_service, number_plate_service
from app.services.hydrotest_status_service import decide_status
from app.utils.date_utils import utc_now
from app.utils.plate_utils import looks_like_plate, normalize_plate, plate_variants

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}
CHUNK_SIZE = 1024 * 1024


def _video_dir() -> Path:
    return config.UPLOAD_DIR / "videos"


def _plate_dir() -> Path:
    return config.UPLOAD_DIR / "plates"


def _get_doc(db, inspection_id: str) -> dict:
    try:
        doc = db["inspection_results"].find_one({"_id": ObjectId(inspection_id)})
    except (InvalidId, TypeError):
        doc = None
    if doc is None:
        raise NotFoundError("Inspection result not found.")
    return doc


def _update(db, inspection_id, fields: dict) -> None:
    fields["updatedAt"] = utc_now()
    db["inspection_results"].update_one({"_id": ObjectId(inspection_id)}, {"$set": fields})


# ---------- upload ----------

def save_upload(db, upload: UploadFile) -> dict:
    original_name = Path(upload.filename or "").name  # drops any folder part
    if not original_name:
        raise BadRequest("No video file was provided.")

    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise BadRequest("Unsupported file type. Please upload an .mp4, .avi, .mov or .mkv video.")

    content_type = (upload.content_type or "").lower()
    if content_type and not (content_type.startswith("video/") or content_type == "application/octet-stream"):
        raise BadRequest("The uploaded file does not look like a video.")

    _video_dir().mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"  # we never use the user's file name on disk
    path = _video_dir() / stored_name
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024

    try:
        size = 0
        with open(path, "wb") as out:
            while chunk := upload.file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise BadRequest(f"The video is too large. The maximum size is {config.MAX_UPLOAD_MB} MB.")
                out.write(chunk)
        if size == 0:
            raise BadRequest("The uploaded video is empty.")
        number_plate_service.check_video(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise

    now = utc_now()
    doc = {
        "videoName": original_name[:200],
        "storedFileName": stored_name,
        "status": InspectionStatus.UPLOADED.value,
        "progress": 0,
        "detectedPlate": None,
        "rawText": None,
        "confidence": None,
        "detectionConfidence": None,
        "lowConfidence": False,
        "manuallyCorrected": False,
        "plateImage": None,
        "assetId": None,
        "hydrotestStatus": None,
        "message": None,
        "createdAt": now,
        "updatedAt": now,
    }
    doc["_id"] = db["inspection_results"].insert_one(doc).inserted_id
    return inspection_to_dict(doc)


# ---------- processing ----------

def prepare_processing(db, inspection_id: str) -> dict:
    """Checks that run before the background job starts, so errors reach the user right away."""
    doc = _get_doc(db, inspection_id)
    if doc["status"] == InspectionStatus.PROCESSING.value:
        raise BadRequest("This video is already being processed.")
    if not (_video_dir() / doc["storedFileName"]).is_file():
        raise NotFoundError("The uploaded video file is no longer available. Please upload it again.")

    number_plate_service.get_model()
    number_plate_service.check_ocr_available()

    _update(db, inspection_id, {"status": InspectionStatus.PROCESSING.value, "progress": 0, "message": None})
    return inspection_to_dict(_get_doc(db, inspection_id))


def process_video(db, inspection_id: str) -> None:
    """Runs in a background task. Progress and the outcome are written to MongoDB."""
    doc = _get_doc(db, inspection_id)
    video_path = _video_dir() / doc["storedFileName"]

    def report_progress(percent: int) -> None:
        _update(db, inspection_id, {"progress": percent})

    try:
        reading = number_plate_service.find_plate_in_video(video_path, report_progress)
    except number_plate_service.NoPlateFound as error:
        _update(db, inspection_id, {"status": InspectionStatus.NO_PLATE.value, "progress": 100, "message": str(error)})
        return
    except AppError as error:
        _update(db, inspection_id, {"status": InspectionStatus.FAILED.value, "message": error.message})
        return
    except Exception:
        logger.exception("Video processing failed for %s", inspection_id)
        _update(db, inspection_id, {"status": InspectionStatus.FAILED.value, "message": "Video processing failed unexpectedly."})
        return

    _plate_dir().mkdir(parents=True, exist_ok=True)
    plate_file = f"{uuid4().hex}.jpg"
    cv2.imwrite(str(_plate_dir() / plate_file), reading.image)

    low_confidence = reading.ocr_confidence < config.OCR_MIN_CONFIDENCE
    message = "OCR confidence is low. Please check the number and correct it if needed." if low_confidence else None
    lookup = lookup_plate(db, reading.text)

    _update(
        db,
        inspection_id,
        {
            "status": InspectionStatus.COMPLETED.value,
            "progress": 100,
            "detectedPlate": reading.text,
            "rawText": reading.raw_text,
            "confidence": round(reading.ocr_confidence, 3),
            "detectionConfidence": round(reading.detection_confidence, 3),
            "lowConfidence": low_confidence,
            "plateImage": plate_file,
            "assetId": lookup["asset"]["assetId"] if lookup["asset"] else None,
            "hydrotestStatus": lookup["hydrotestStatus"].value,
            "message": message,
        },
    )


# ---------- lookup / results ----------

def lookup_plate(db, identifier: str) -> dict:
    plate = normalize_plate(identifier)
    if not plate:
        raise BadRequest("Please enter a valid number plate or asset reference.")

    # GJ01AB1234 / GJ1AB1234 / "gj 01 ab-1234" are the same registration: try each spelling
    asset_doc = None
    for spelling in plate_variants(identifier) or [identifier]:
        asset_doc = asset_service.find_by_identifier(db, spelling)
        if asset_doc:
            break
    latest = hydrotest_service.latest_record(db, asset_doc["assetId"]) if asset_doc else None
    status = decide_status(asset_doc, latest)

    if asset_doc:
        asset_doc["status"] = status.value
    return {
        "plateNumber": plate,
        "found": asset_doc is not None,
        "hydrotestStatus": status,
        "asset": asset_to_dict(asset_doc) if asset_doc else None,
        "latestHydrotest": record_to_dict(latest) if latest else None,
    }


def get_result(db, inspection_id: str) -> dict:
    doc = _get_doc(db, inspection_id)
    result = inspection_to_dict(doc)
    # looked up again on every read so the status is always current
    result["lookup"] = lookup_plate(db, doc["detectedPlate"]) if doc.get("detectedPlate") else None
    return result


def correct_plate(db, inspection_id: str, plate_number: str) -> dict:
    doc = _get_doc(db, inspection_id)
    if doc["status"] in (InspectionStatus.UPLOADED.value, InspectionStatus.PROCESSING.value):
        raise BadRequest("Wait until the video has been processed before correcting the number.")

    lookup = lookup_plate(db, plate_number)
    _update(
        db,
        inspection_id,
        {
            "status": InspectionStatus.COMPLETED.value,
            "detectedPlate": lookup["plateNumber"],
            "manuallyCorrected": True,
            "lowConfidence": False,
            "message": None,
            "assetId": lookup["asset"]["assetId"] if lookup["asset"] else None,
            "hydrotestStatus": lookup["hydrotestStatus"].value,
        },
    )
    return get_result(db, inspection_id)


def get_plate_image_path(db, inspection_id: str) -> Path:
    doc = _get_doc(db, inspection_id)
    name = doc.get("plateImage")
    path = _plate_dir() / name if name else None
    if path is None or not path.is_file():
        raise NotFoundError("No plate image is available for this inspection.")
    return path

# ---------- live camera frames ----------

def detect_plate_quick(data: bytes, full_width: int | None = None) -> dict:
    """Fast YOLO-only check of a small camera frame: is the whole plate in view, big and sharp enough?
    The live camera calls this several times a second and only takes the real photo when `ready` is true."""
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise BadRequest("The image could not be read. Please send a JPG, PNG or WebP photo.")
    number_plate_service.get_model()
    return number_plate_service.detect_plate_quality(frame, full_width=full_width)


def scan_frame(db, data: bytes, save: bool = False) -> dict:
    """One camera frame -> plate detection -> OCR -> hydrotest lookup.
    save=False: quick check while the camera runs (nothing stored).
    save=True : stored as an inspection, same as a video result."""
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise BadRequest("The image could not be read. Please send a JPG, PNG or WebP photo.")

    number_plate_service.get_model()
    number_plate_service.check_ocr_available()

    try:
        reading = number_plate_service.find_plate_in_frame(frame)
    except number_plate_service.NoPlateFound as error:
        return {"plateDetected": False, "message": str(error), "inspection": None}

    low_confidence = reading.ocr_confidence < config.OCR_MIN_CONFIDENCE
    out = {
        "plateDetected": True,
        "plateNumber": reading.text,
        "ocrConfidence": round(reading.ocr_confidence, 3),
        "detectionConfidence": round(reading.detection_confidence, 3),
        "lowConfidence": low_confidence,
        "plateFormatValid": looks_like_plate(reading.text),
        "message": "OCR confidence is low. Please check the number and correct it if needed." if low_confidence else None,
        "inspection": None,
    }
    if not save:
        return out

    _plate_dir().mkdir(parents=True, exist_ok=True)
    plate_file = f"{uuid4().hex}.jpg"
    cv2.imwrite(str(_plate_dir() / plate_file), reading.image)
    lookup = lookup_plate(db, reading.text)
    now = utc_now()
    doc = {
        "videoName": "Live camera capture",
        "storedFileName": "",
        "status": InspectionStatus.COMPLETED.value,
        "progress": 100,
        "detectedPlate": reading.text,
        "rawText": reading.raw_text,
        "confidence": out["ocrConfidence"],
        "detectionConfidence": out["detectionConfidence"],
        "lowConfidence": low_confidence,
        "manuallyCorrected": False,
        "plateImage": plate_file,
        "assetId": lookup["asset"]["assetId"] if lookup["asset"] else None,
        "hydrotestStatus": lookup["hydrotestStatus"].value,
        "message": out["message"],
        "createdAt": now,
        "updatedAt": now,
    }
    doc["_id"] = db["inspection_results"].insert_one(doc).inserted_id
    out["inspection"] = get_result(db, str(doc["_id"]))
    return out