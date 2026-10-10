"""Runs the real frame sampling, preprocessing and OCR code.

The YOLO model itself is replaced by a small stand-in that returns the known
position of a plate we draw ourselves, so no weights file is needed.
Skipped automatically when Tesseract is not installed.
"""
import cv2
import numpy as np
import pytest

from app.errors import ServiceUnavailable
from app.services import number_plate_service as service

try:
    import pytesseract

    pytesseract.get_tesseract_version()
    HAS_TESSERACT = True
except Exception:
    HAS_TESSERACT = False

needs_tesseract = pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract is not installed")

PLATE_BOX = (60, 80, 360, 170)  # x1, y1, x2, y2


def draw_frame(text="GJ01AB1234"):
    frame = np.full((300, 420, 3), 90, dtype=np.uint8)
    x1, y1, x2, y2 = PLATE_BOX
    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), -1)
    cv2.putText(frame, text, (x1 + 8, y2 - 35), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 4)
    return frame


class FakeBoxes(list):
    pass


class FakeBox:
    def __init__(self, xyxy, conf):
        self.xyxy = np.array([xyxy])
        self.conf = np.array([conf])


class FakeModel:
    """Stands in for ultralytics.YOLO: returns one box per frame."""

    def __init__(self, found=True):
        self.found = found
        self.frames_seen = 0

    def predict(self, frame, conf, verbose):
        self.frames_seen += 1
        result = type("Result", (), {})()
        result.boxes = [FakeBox(PLATE_BOX, 0.9)] if self.found else []
        return [result]


def write_video(path, frames=20, text="GJ01AB1234"):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (420, 300))
    for _ in range(frames):
        writer.write(draw_frame(text))
    writer.release()


def test_preprocess_returns_several_variants():
    crop = draw_frame()[80:170, 60:360]
    names = [name for name, _ in service.preprocess_variants(crop)]
    assert {"grayscale", "otsu", "adaptive", "sharpened"} <= set(names)


def test_only_every_nth_frame_is_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(service.config, "FRAME_SKIP", 5)
    video = tmp_path / "v.avi"
    write_video(video, frames=20)
    model = FakeModel(found=False)
    service.extract_detections(video, model)
    assert model.frames_seen == 4  # frames 0, 5, 10, 15


def test_no_detection_raises_no_plate_found(tmp_path):
    video = tmp_path / "v.avi"
    write_video(video)
    with pytest.raises(service.NoPlateFound) as error:
        service.find_plate_in_video(video, model=FakeModel(found=False))
    assert "No number plate could be detected" in str(error.value)


@needs_tesseract
def test_reads_plate_from_video(tmp_path):
    video = tmp_path / "v.avi"
    write_video(video)
    progress = []
    reading = service.find_plate_in_video(video, progress.append, model=FakeModel())
    assert reading.text == "GJ01AB1234"
    assert 0 < reading.ocr_confidence <= 1
    assert reading.detection_confidence == 0.9
    assert progress and progress[-1] >= 80


def test_missing_model_file_gives_config_error(tmp_path, monkeypatch):
    monkeypatch.setattr(service.config, "YOLO_MODEL_PATH", tmp_path / "nope.pt")
    monkeypatch.setattr(service, "_model", None)
    with pytest.raises(ServiceUnavailable) as error:
        service.get_model()
    assert "Number plate detection model is not configured" in error.value.message
