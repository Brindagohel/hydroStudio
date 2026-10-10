"""Camera frame / video -> YOLO plate detection -> image enhancement -> EasyOCR -> Indian plate fixing.

Nothing in here is faked: if the YOLO weights or EasyOCR are missing we
raise a clear error instead of inventing a plate number.

A reading is only returned when it can be trusted: the whole plate is inside the picture, the crop is sharp
enough, the text is a complete valid plate (known state code) and it is confirmed (two OCR passes agree, or one
pass is very confident). Otherwise NoPlateFound is raised and the camera simply takes another photo.
"""
import logging
import math
import threading
from dataclasses import dataclass

import cv2
import numpy as np

from app import config
from app.errors import BadRequest, ServiceUnavailable
from app.utils.plate_utils import fix_indian_plate, looks_like_plate, normalize_plate

logger = logging.getLogger(__name__)

PLATE_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
MIN_PLATE_LENGTH = 4
LOW_LIGHT_LEVEL = 85          # median brightness (0-255) below this = "low light"
MIN_OCR_HEIGHT = 200          # plate crops are enlarged to at least this height before OCR
MIN_GOOD_CROP_WIDTH = 110     # a crop narrower than this is too small to count as "good"
VIDEO_CANDIDATES = 10         # best detections of a whole video that are read with OCR
LIVE_CANDIDATES = 2           # live camera: only the best crops are read (speed)
FAST_OCR_VARIANTS = 3         # live camera: how many preprocessed versions are tried at most
EARLY_STOP_DETECTIONS = 10    # video: stop scanning once this many good detections are collected
EARLY_STOP_CONFIDENCE = 0.5
MIN_ASPECT = 1.0              # plate box width / height: two-line plates are ~1-2.5, one-line ~3-6
MAX_ASPECT = 7.5

# Indian state / union-territory codes: the first two characters of a registration number
STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HP", "HR", "JH", "JK", "KA", "KL",
    "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}

_model = None
_reader = None
# one YOLO / OCR call at a time: the live camera and a video upload can run together
_model_lock = threading.Lock()
_ocr_lock = threading.Lock()


class NoPlateFound(Exception):
    """The image/video was processed fine, but no usable plate came out of it."""


@dataclass
class Detection:
    confidence: float
    image: np.ndarray
    frame_number: int
    sharpness: float = 100.0  # higher = sharper crop
    box: tuple | None = None  # (x1, y1, x2, y2) as fractions 0..1 of the frame

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def rank(self) -> float:
        """Big, sharp, confident crops are read first."""
        size_factor = 0.3 + 0.7 * min(1.0, self.width / 160.0)
        sharp_factor = 0.5 + 0.5 * min(1.0, self.sharpness / 100.0)
        return self.confidence * sharp_factor * size_factor


@dataclass
class PlateReading:
    text: str
    raw_text: str
    ocr_confidence: float
    detection_confidence: float
    image: np.ndarray
    votes: int = 1  # how many OCR passes (image versions / frames) gave exactly this text

    @property
    def score(self) -> float:
        # a result that looks like a real plate beats a higher-confidence guess that doesn't
        return self.ocr_confidence + (1.0 if looks_like_plate(self.text) else 0.0)


# ---------- setup checks ----------

def get_model():
    """Load the YOLO model once and reuse it."""
    global _model
    if _model is not None:
        return _model

    if not config.YOLO_MODEL_PATH.is_file():
        raise ServiceUnavailable(
            "Number plate detection model is not configured. "
            "Place a YOLO weights file at the path set in YOLO_MODEL_PATH (default: models/number_plate_model.pt)."
        )
    try:
        from ultralytics import YOLO
    except ImportError:
        raise ServiceUnavailable("The 'ultralytics' package is not installed, so number plate detection is unavailable.")

    _model = YOLO(str(config.YOLO_MODEL_PATH))
    return _model


def check_ocr_available() -> None:
    try:
        import easyocr  # noqa: F401
    except ImportError:
        raise ServiceUnavailable("The OCR engine (easyocr) is not installed. Run: pip install easyocr")


def get_reader():
    """Load EasyOCR once and reuse it (the first call downloads the models)."""
    global _reader
    if _reader is None:
        try:
            import easyocr
        except ImportError:
            raise ServiceUnavailable("The OCR engine (easyocr) is not installed. Run: pip install easyocr")
        try:
            import torch

            use_gpu = torch.cuda.is_available()
        except Exception:
            use_gpu = False
        _reader = easyocr.Reader(["en"], gpu=use_gpu)
    return _reader


def warmup() -> None:
    """Called once at server start (see main.py) so the first camera scan is not slow."""
    try:
        get_model()
        get_reader()
        logger.info("Number plate model and OCR engine are loaded.")
    except Exception as error:  # the real error is shown later, when someone actually scans
        logger.warning("Model warm-up skipped: %s", getattr(error, "message", error))


def check_video(path) -> None:
    """Make sure OpenCV can open the file and read at least one frame."""
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise BadRequest("The video could not be opened. The file may be corrupted.")
        ok, _ = cap.read()
        if not ok:
            raise BadRequest("The video has no readable frames. It may be empty or corrupted.")
    finally:
        cap.release()


# ---------- low light / quality helpers ----------

def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image


def is_low_light(image: np.ndarray) -> bool:
    return float(np.median(_gray(image))) < LOW_LIGHT_LEVEL


def _gamma_lut(mean_level: float) -> np.ndarray:
    """Brightening curve that pulls a dark image towards mid-grey (no change if already bright)."""
    mean_level = min(max(mean_level, 8.0), 255.0)
    gamma = math.log(0.5) / math.log(mean_level / 255.0) if mean_level < 128 else 1.0
    gamma = min(max(gamma, 0.35), 1.0)  # gamma < 1 brightens
    return np.array([((i / 255.0) ** gamma) * 255 for i in range(256)], dtype=np.uint8)


def enhance_frame(frame: np.ndarray) -> np.ndarray:
    """Make a dark / low-contrast camera frame easier for YOLO: brighten, then local contrast (CLAHE)."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    light = cv2.LUT(light, _gamma_lut(float(np.median(light))))
    light = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(light)
    return cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)


def measure_sharpness(crop: np.ndarray) -> float:
    """Edge strength of a crop. Contrast-stretched and size-normalised so dark and big/small crops compare fairly."""
    gray = _gray(crop)
    if gray.size == 0:
        return 0.0
    height, width = gray.shape[:2]
    if width != 200:
        gray = cv2.resize(gray, (200, max(8, int(height * 200 / width))), interpolation=cv2.INTER_AREA)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def touches_edge(box: tuple | None) -> bool:
    """True when the plate box reaches the edge of the picture (so part of the plate may be cut off)."""
    if box is None:
        return False
    x1, y1, x2, y2 = box
    m = config.READY_EDGE_MARGIN
    return not (x1 >= m and y1 >= m and x2 <= 1 - m and y2 <= 1 - m)


# ---------- detection ----------

def crop_with_padding(frame: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
    height, width = frame.shape[:2]
    pad_x = int((x2 - x1) * 0.06)
    pad_y = int((y2 - y1) * 0.12)
    left, right = max(0, x1 - pad_x), min(width, x2 + pad_x)
    top, bottom = max(0, y1 - pad_y), min(height, y2 + pad_y)
    return frame[top:bottom, left:right]


def _yolo_boxes(model, image: np.ndarray, conf: float, imgsz: int | None = None) -> list[tuple[int, int, int, int, float]]:
    with _model_lock:
        results = model.predict(image, conf=conf, imgsz=imgsz or config.YOLO_IMGSZ, verbose=False)
    boxes = []
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            boxes.append((x1, y1, x2, y2, float(box.conf[0])))
    return boxes


def detect_in_frame(model, frame: np.ndarray, frame_number: int, retry: bool = True) -> list[Detection]:
    """YOLO on one frame. If nothing is found and `retry` is on, look again on a brightened copy of the
    frame with a lower confidence threshold and a bigger input size (dark, blurry or far-away plates)."""
    source, boxes = frame, _yolo_boxes(model, frame, config.YOLO_CONFIDENCE)
    if not boxes and retry:
        source = enhance_frame(frame)
        boxes = _yolo_boxes(model, source, config.YOLO_FALLBACK_CONFIDENCE, max(config.YOLO_IMGSZ, 960))

    height, width = source.shape[:2]
    found = []
    for x1, y1, x2, y2, conf in boxes:
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = crop_with_padding(source, x1, y1, x2, y2)
        if crop.size > 0:
            found.append(
                Detection(conf, crop, frame_number, measure_sharpness(crop), (x1 / width, y1 / height, x2 / width, y2 / height))
            )
    return found


def detect_plate_quality(frame: np.ndarray, full_width: int | None = None) -> dict:
    """Quick YOLO-only check used by the live camera (no OCR).

    Tells the browser whether the WHOLE plate is in view, big enough and sharp enough to take the real photo.
    `frame` is a small preview; `full_width` is the width of the real camera picture (for the size check).
    The box is returned as fractions (0-1) of the frame so the browser can draw it.
    """
    model = get_model()
    height, width = frame.shape[:2]
    full_width = full_width or width
    low_light = is_low_light(frame)

    # low threshold on purpose: we want to SEE the plate to guide the user, then judge its quality below
    boxes = _yolo_boxes(model, frame, config.YOLO_FALLBACK_CONFIDENCE)
    if not boxes and low_light:
        boxes = _yolo_boxes(model, enhance_frame(frame), config.YOLO_FALLBACK_CONFIDENCE, max(config.YOLO_IMGSZ, 960))

    result = {
        "plateDetected": False, "ready": False, "complete": False, "lowLight": low_light,
        "box": None, "confidence": 0.0, "plateWidthPx": 0, "sharpness": 0.0,
        "message": "No number plate in view. Point the camera at the plate."
        + (" It is dark: add light if you can." if low_light else ""),
    }
    if not boxes:
        return result

    x1, y1, x2, y2, conf = max(boxes, key=lambda b: b[4])
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        return result

    complete = not touches_edge((x1 / width, y1 / height, x2 / width, y2 / height))
    plate_px = (x2 - x1) / width * full_width
    aspect = (x2 - x1) / max(1, (y2 - y1))
    sharpness = measure_sharpness(frame[y1:y2, x1:x2])

    # dark pictures are noisier and less certain, so the bar is a little lower
    relax = 0.7 if low_light else 1.0
    min_conf = config.READY_MIN_DETECTION_CONF * relax
    min_width = max(config.READY_MIN_PLATE_WIDTH_PX, config.READY_MIN_PLATE_WIDTH_RATIO * full_width)
    min_sharp = config.READY_MIN_SHARPNESS * relax

    ready = False
    if not complete:
        message = "The plate is cut off at the edge. Keep the whole plate inside the picture."
    elif plate_px < min_width:
        message = "Move closer to the number plate."
    elif not MIN_ASPECT <= aspect <= MAX_ASPECT:
        message = "Face the plate straight on. Part of it may be hidden or tilted."
    elif conf < min_conf:
        message = "Plate not clear yet. Improve the light or the angle."
    elif sharpness < min_sharp:
        message = f"The picture is too blurry (sharpness {int(sharpness)}, needs {int(min_sharp)}). Hold steady and let the camera focus."
    else:
        message = f"Plate is clear (sharpness {int(sharpness)}). Hold steady..."
        ready = True

    result.update({
        "plateDetected": True,
        "complete": complete,
        "ready": ready,
        "box": {"x": x1 / width, "y": y1 / height, "w": (x2 - x1) / width, "h": (y2 - y1) / height},
        "confidence": round(conf, 3),
        "plateWidthPx": int(plate_px),
        "sharpness": round(sharpness, 1),
        "message": message,
    })
    return result


def _scan_video(video_path, model, on_progress, retry: bool) -> list[Detection]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise BadRequest("The video could not be opened. The file may be corrupted.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    detections = []
    good = 0  # detections that are confident AND big enough to read well
    frame_number = 0
    stopped_early = False
    try:
        while cap.grab():  # grab() skips decoding, so skipped frames are cheap
            if frame_number % config.FRAME_SKIP == 0:
                ok, frame = cap.retrieve()
                if ok:
                    found = detect_in_frame(model, frame, frame_number, retry=retry)
                    detections.extend(found)
                    good += sum(
                        1 for d in found
                        if d.confidence >= EARLY_STOP_CONFIDENCE and d.width >= MIN_GOOD_CROP_WIDTH
                    )
                    if good >= EARLY_STOP_DETECTIONS:
                        # enough big, good crops: no need to decode the rest of the video
                        stopped_early = True
                        frame_number += 1
                        break
            frame_number += 1
            if on_progress and total_frames > 0 and frame_number % 10 == 0:
                on_progress(min(int(frame_number / total_frames * 80), 80))
    finally:
        cap.release()

    if frame_number == 0:
        raise BadRequest("The video has no readable frames. It may be empty or corrupted.")
    if stopped_early and on_progress:
        on_progress(80)
    return detections


def extract_detections(video_path, model, on_progress=None) -> list[Detection]:
    """Run YOLO on every FRAME_SKIP-th frame and keep the best (big + confident + sharp) plates.
    Stops early once enough big, good plates are found. If the normal pass finds nothing, a second pass
    brightens each frame and uses a lower threshold."""
    detections = _scan_video(video_path, model, on_progress, retry=False)
    if not detections:
        detections = _scan_video(video_path, model, on_progress, retry=True)
    detections.sort(key=lambda d: d.rank, reverse=True)
    return detections[: max(config.PLATE_CANDIDATES, VIDEO_CANDIDATES)]


# ---------- preprocessing + OCR ----------

def _upscale(gray: np.ndarray) -> np.ndarray:
    height = gray.shape[0]
    if height < MIN_OCR_HEIGHT:
        scale = MIN_OCR_HEIGHT / height
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return gray


def iter_variants(crop: np.ndarray, fast: bool = False):
    """Yield cleaned-up versions of the plate crop ONE AT A TIME (best guesses first), so the caller can stop
    after the first good OCR reading without paying for the versions it never uses.

    Handles the usual camera problems: tiny crop (enlarged), dark (brightened), flat contrast (CLAHE),
    blur (sharpened), screen/moire pattern (smoothed) and uneven light (thresholded).
    `fast` = only the first few, cheapest versions (live camera).
    """
    gray = _upscale(_gray(crop))
    if float(np.median(gray)) < LOW_LIGHT_LEVEL:
        gray = cv2.LUT(gray, _gamma_lut(float(np.median(gray))))
    # a small margin around the text helps the OCR find the first and last characters
    gray = cv2.copyMakeBorder(gray, 12, 12, 16, 16, cv2.BORDER_REPLICATE)

    denoised = cv2.bilateralFilter(gray, 9, 60, 60)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4)).apply(denoised)
    yield "clahe", clahe
    yield "grayscale", gray

    blurred = cv2.GaussianBlur(clahe, (0, 0), 2.0)
    sharpened = cv2.addWeighted(clahe, 1.8, blurred, -0.8, 0)  # unsharp mask
    yield "sharpened", sharpened
    if fast:
        return

    smooth = cv2.GaussianBlur(gray, (5, 5), 0)  # kills the grid pattern of a phone / monitor screen
    smooth = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(smooth)
    yield "smooth", smooth

    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield "otsu", otsu
    adaptive = cv2.adaptiveThreshold(clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)
    yield "adaptive", adaptive


def preprocess_variants(crop: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """All variants as a list (kept for any other code that imports it)."""
    return list(iter_variants(crop))


def run_ocr(image: np.ndarray) -> tuple[str, float]:
    """Returns (text, confidence between 0 and 1). Empty text means nothing was read."""
    reader = get_reader()
    try:
        with _ocr_lock:
            results = reader.readtext(
                image,
                allowlist=PLATE_CHARACTERS,
                detail=1,
                paragraph=False,
                text_threshold=0.5,   # accept fainter text (low light)
                low_text=0.3,
                contrast_ths=0.2,     # let EasyOCR boost low-contrast pieces itself
                adjust_contrast=0.7,
                width_ths=0.9,        # keep "GJ 06" and "PA 0001" in one line
            )
    except Exception:
        logger.warning("EasyOCR failed on one image variant", exc_info=True)
        return "", 0.0
    if not results:
        return "", 0.0

    # read in plate order: top row first, then left to right (two-line plates exist)
    height = image.shape[0]

    def order(item):
        box = item[0]
        x_left = min(p[0] for p in box)
        y_center = sum(p[1] for p in box) / len(box)
        return (0 if y_center < height * 0.5 else 1, x_left)

    results = sorted(results, key=order)
    text = "".join(r[1] for r in results)
    total_chars = sum(len(r[1]) for r in results) or 1
    confidence = sum(float(r[2]) * len(r[1]) for r in results) / total_chars  # long pieces count more
    return text, confidence


def trim_to_plate(text: str) -> str:
    """Turn the raw OCR text into the most believable plate.

    OCR often adds stray characters at the edges (frame, bolts, a logo) and mixes up look-alikes (O/0, I/1).
    Every window of 8-11 characters is tried; the valid-looking plate that needs the FEWEST edits wins
    (a swapped look-alike costs 1, a character cut from the ends costs 1, an unknown state code costs 3).
    Characters are never invented.
    """
    plain = normalize_plate(text)
    fallback = fix_indian_plate(plain)
    if len(plain) < 8:
        return fallback

    best, best_cost = None, None
    for length in range(min(len(plain), 11), 7, -1):
        for start in range(0, len(plain) - length + 1):
            window = plain[start:start + length]
            fixed = fix_indian_plate(window)
            if not looks_like_plate(fixed):
                continue
            swaps = sum(a != b for a, b in zip(window, fixed)) + abs(len(window) - len(fixed))
            cost = swaps + (len(plain) - length) + (0 if fixed[:2] in STATE_CODES else 3)
            if best_cost is None or cost < best_cost:
                best, best_cost = fixed, cost
    return best or fallback


def read_plate(detection: Detection, fast: bool = False) -> PlateReading | None:
    """OCR the preprocessed versions of one crop and keep the text they agree on.

    Stops early when one version is very sure, or when two versions agree on the same valid plate.
    `fast` (live camera) tries at most FAST_OCR_VARIANTS versions. `votes` on the result tells how many
    versions agreed, which is what the trust check at the end relies on.
    """
    tally: dict[str, float] = {}
    best_per_text: dict[str, PlateReading] = {}
    agreeing: dict[str, int] = {}
    sure_enough = config.OCR_SURE_CONFIDENCE

    for name, image in iter_variants(detection.image, fast=fast):
        raw_text, confidence = run_ocr(image)
        text = trim_to_plate(raw_text)  # fixes look-alikes like O/0, S/5 by position
        if len(text) < MIN_PLATE_LENGTH:
            continue
        reading = PlateReading(text, raw_text, confidence, detection.confidence, detection.image)
        tally[text] = tally.get(text, 0.0) + reading.score
        agreeing[text] = agreeing.get(text, 0) + 1
        if text not in best_per_text or reading.score > best_per_text[text].score:
            best_per_text[text] = reading
        if looks_like_plate(text) and (confidence >= sure_enough or agreeing[text] >= 2):
            best_per_text[text].votes = agreeing[text]
            return best_per_text[text]

    if not tally:
        return None
    winner = max(tally, key=lambda t: (agreeing[t], tally[t], best_per_text[t].ocr_confidence))
    best_per_text[winner].votes = agreeing[winner]
    return best_per_text[winner]


# ---------- main entry points ----------

def consensus_plate(readings: list[PlateReading]) -> PlateReading | None:
    """Combine readings of the same plate from different frames with a per-character vote."""
    if not readings:
        return None
    pool = [r for r in readings if looks_like_plate(r.text)] or readings
    length_votes: dict[int, float] = {}
    for r in pool:
        length_votes[len(r.text)] = length_votes.get(len(r.text), 0.0) + r.score
    length = max(length_votes, key=length_votes.get)
    same = [r for r in pool if len(r.text) == length]
    best = max(same, key=lambda r: r.score)

    chars = []
    for position in range(length):
        weights: dict[str, float] = {}
        for r in same:
            ch = r.text[position]
            weights[ch] = weights.get(ch, 0.0) + max(r.ocr_confidence, 0.05)
        chars.append(max(weights, key=weights.get))
    voted = fix_indian_plate("".join(chars))

    if voted == best.text or not looks_like_plate(voted):
        best.votes = max(best.votes, sum(r.votes for r in same if r.text == best.text))
        return best
    agree = [r for r in same if r.text == voted]
    confidence = sum(r.ocr_confidence for r in agree) / len(agree) if agree else best.ocr_confidence
    return PlateReading(voted, best.raw_text, confidence, best.detection_confidence, best.image,
                        votes=sum(r.votes for r in agree) or 1)


def _best_reading(detections: list[Detection], on_progress=None, fast: bool = False) -> PlateReading | None:
    """Read the candidate crops and combine them. Video stops once 3 different frames give the same valid plate."""
    readings: list[PlateReading] = []
    seen: dict[str, int] = {}
    for index, detection in enumerate(detections):
        reading = read_plate(detection, fast=fast)
        if reading:
            readings.append(reading)
            seen[reading.text] = seen.get(reading.text, 0) + 1
            if looks_like_plate(reading.text):
                if fast and (reading.votes >= 2 or reading.ocr_confidence >= config.OCR_SURE_CONFIDENCE):
                    break
                if seen[reading.text] >= 3:
                    break
        if on_progress:
            on_progress(80 + int((index + 1) / len(detections) * 19))
    return consensus_plate(readings)


def untrusted_reason(reading: PlateReading) -> str | None:
    """Why this reading must NOT be shown as a result (None = it can be trusted)."""
    if not looks_like_plate(reading.text):
        return "The text read from the plate is not a complete registration number."
    if reading.text[:2] not in STATE_CODES:
        return "The state code on the plate could not be read reliably."
    if reading.votes < 2 and reading.ocr_confidence < config.OCR_SURE_CONFIDENCE:
        return "The number is not clear enough to read reliably."
    return None


def find_plate_in_video(video_path, on_progress=None, model=None) -> PlateReading:
    model = model or get_model()
    detections = extract_detections(video_path, model, on_progress)
    if not detections:
        raise NoPlateFound(
            "No number plate could be detected. Please upload a clearer video or enter the asset/reference number manually."
        )

    best = _best_reading(detections, on_progress)
    if best is None:
        raise NoPlateFound(
            "A number plate was found but its text could not be read. Please upload a clearer video or enter the number manually."
        )
    return best


def find_plate_in_frame(frame: np.ndarray, model=None) -> PlateReading:
    """Single image / live camera snapshot: YOLO (ONE pass) -> checks -> crop -> fast OCR -> trust check.

    The live camera already found the plate in its preview, so the slow brightened second YOLO pass is only
    used when the picture is really dark. A blurry, cut-off or doubtful plate is REJECTED here (NoPlateFound)
    instead of returning a guess: the camera simply takes the next photo.
    """
    model = model or get_model()
    low_light = is_low_light(frame)
    detections = detect_in_frame(model, frame, 0, retry=low_light)
    if not detections:
        raise NoPlateFound("No number plate could be detected in this image. Move closer, hold steady and try again.")

    # 1. the whole plate must be inside the picture and have a plate-like shape
    whole = [d for d in detections if not touches_edge(d.box)]
    if not whole:
        raise NoPlateFound("The plate is cut off at the edge of the picture. Keep the whole plate in view.")
    shaped = [d for d in whole if d.box and MIN_ASPECT <= (d.box[2] - d.box[0]) * frame.shape[1] / max(1.0, (d.box[3] - d.box[1]) * frame.shape[0]) <= MAX_ASPECT]
    if not shaped:
        raise NoPlateFound("The plate looks partly hidden or tilted. Face it straight on and try again.")

    # 2. the plate must be sharp enough to read (dark pictures get a little less strict)
    min_sharp = config.MIN_READ_SHARPNESS * (0.7 if low_light else 1.0)
    sharp = [d for d in shaped if d.sharpness >= min_sharp]
    if not sharp:
        best_value = int(max(d.sharpness for d in shaped))
        raise NoPlateFound(
            f"The plate is too blurry to read reliably (sharpness {best_value}, needs {int(min_sharp)}). Hold steady and let the camera focus."
        )

    sharp.sort(key=lambda d: d.rank, reverse=True)
    best = _best_reading(sharp[:LIVE_CANDIDATES], fast=True)
    if best is None:
        raise NoPlateFound("A number plate was found but its text could not be read. Try again with better light.")

    # 3. only a complete, valid, confirmed reading is returned
    reason = untrusted_reason(best)
    if reason:
        raise NoPlateFound(f"{reason} Taking another photo...")
    return best