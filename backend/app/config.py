"""All settings are read from environment variables (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

# project-root/backend/app/config.py -> project root is two folders up from "app"
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / "backend" / ".env")


def _resolve(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else BASE_DIR / path


MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "hydrotest_db")

YOLO_MODEL_PATH = _resolve(os.getenv("YOLO_MODEL_PATH", "models/number_plate_model.pt"))
YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.40"))
FRAME_SKIP = max(1, int(os.getenv("FRAME_SKIP", "5")))
OCR_MIN_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "0.60"))
# how many of the best detections we try to read with OCR (each extra one costs time)
PLATE_CANDIDATES = int(os.getenv("PLATE_CANDIDATES", "2"))

# ---- speed / quality tuning for number-plate reading ----
# Frames are shrunk to this width before YOLO runs (the crop is still taken from the full-size frame).
DETECT_MAX_WIDTH = int(os.getenv("DETECT_MAX_WIDTH", "960"))
YOLO_IMGSZ = int(os.getenv("YOLO_IMGSZ", "640"))
# Second chance with a lower threshold when the normal one finds nothing in a still photo
YOLO_FALLBACK_CONFIDENCE = float(os.getenv("YOLO_FALLBACK_CONFIDENCE", "0.20"))
# OCR stops trying other image versions as soon as one reading is a valid plate with this confidence
OCR_FAST_ACCEPT = float(os.getenv("OCR_FAST_ACCEPT", "0.55"))
# Load YOLO + EasyOCR when the server starts so the first scan is not slow
PRELOAD_MODELS = os.getenv("PRELOAD_MODELS", "true").strip().lower() in ("1", "true", "yes")

# ---- "is the plate fully visible?" check used by the live camera ----
READY_MIN_DETECTION_CONF = float(os.getenv("READY_MIN_DETECTION_CONF", "0.50"))
READY_MIN_PLATE_WIDTH_PX = int(os.getenv("READY_MIN_PLATE_WIDTH_PX", "110"))   # in the full-size frame
READY_MIN_PLATE_WIDTH_RATIO = float(os.getenv("READY_MIN_PLATE_WIDTH_RATIO", "0.10"))  # of the frame width
READY_MIN_SHARPNESS = float(os.getenv("READY_MIN_SHARPNESS", "300"))  # live camera: blurrier than this is not captured
READY_EDGE_MARGIN = float(os.getenv("READY_EDGE_MARGIN", "0.015"))  # plate must be this far from the frame edge

# ---- "is this reading trustworthy?" (stops blurry / half-visible plates giving a false result) ----
# The cropped plate of the captured photo must be at least this sharp (0 = do not check). Dark photos get 30% less.
MIN_READ_SHARPNESS = float(os.getenv("MIN_READ_SHARPNESS", "200"))
# A reading is accepted when two OCR passes agree on it, or when one pass is at least this confident.
OCR_SURE_CONFIDENCE = float(os.getenv("OCR_SURE_CONFIDENCE", "0.85"))

UPLOAD_DIR = _resolve(os.getenv("UPLOAD_DIR", "uploads"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))

DUE_SOON_DAYS = int(os.getenv("DUE_SOON_DAYS", "30"))
TEST_VALIDITY_DAYS = int(os.getenv("TEST_VALIDITY_DAYS", "365"))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

# ---- vehicle details source ("mock" for demo data, "http" for a real API) ----
VEHICLE_PROVIDER = os.getenv("VEHICLE_PROVIDER", "mock").strip().lower()
VEHICLE_API_URL = os.getenv("VEHICLE_API_URL", "").strip()  # must contain {plate}
VEHICLE_API_KEY = os.getenv("VEHICLE_API_KEY", "").strip()
VEHICLE_API_KEY_HEADER = os.getenv("VEHICLE_API_KEY_HEADER", "Authorization").strip()
VEHICLE_API_TIMEOUT = float(os.getenv("VEHICLE_API_TIMEOUT", "10"))

# ---- CNG cylinder rules ----
# Re-test interval used when a test record has no explicit next-due date.
# Confirm the current rule for your region (in India: PESO / Gas Cylinder Rules) before relying on it.
CNG_TEST_VALIDITY_YEARS = int(os.getenv("CNG_TEST_VALIDITY_YEARS", "3"))
MAX_IMAGE_MB = int(os.getenv("MAX_IMAGE_MB", "10"))