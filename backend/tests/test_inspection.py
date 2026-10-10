import io

import cv2
import numpy as np

from app import config
from tests.conftest import asset_payload, record_payload

ASSETS = "/api/hydrotests/assets"


def make_video(path, frames=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 120))
    for _ in range(frames):
        writer.write(np.full((120, 160, 3), 120, dtype=np.uint8))
    writer.release()


def test_lookup_known_asset(client):
    client.post(ASSETS, json=asset_payload(assetId="GJ01AB1234", serialNumber="SN-9"))
    client.post("/api/hydrotests/records", json=record_payload(assetId="GJ01AB1234", testDate="2026-01-01", nextDueDate="2099-01-01"))
    body = client.get("/api/inspection/assets/gj-01-ab-1234").json()
    assert body["found"] is True
    assert body["plateNumber"] == "GJ01AB1234"
    assert body["hydrotestStatus"] == "VALID"
    assert body["latestHydrotest"]["result"] == "Pass"


def test_lookup_unknown_plate_is_not_found(client):
    body = client.get("/api/inspection/assets/ZZ99ZZ9999").json()
    assert body["found"] is False
    assert body["hydrotestStatus"] == "NOT_FOUND"


def test_lookup_with_only_symbols_is_rejected(client):
    assert client.get("/api/inspection/assets/---").status_code == 400


def test_upload_rejects_wrong_extension(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    response = client.post("/api/inspection/upload-video", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


def test_upload_rejects_empty_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    response = client.post("/api/inspection/upload-video", files={"file": ("a.mp4", b"", "video/mp4")})
    assert response.status_code == 400


def test_upload_rejects_corrupted_video(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    response = client.post("/api/inspection/upload-video", files={"file": ("a.mp4", b"not really a video" * 20, "video/mp4")})
    assert response.status_code == 400
    assert list((tmp_path / "videos").glob("*")) == []  # bad file was removed


def test_upload_rejects_oversized_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    response = client.post("/api/inspection/upload-video", files={"file": ("a.mp4", b"x" * 100, "video/mp4")})
    assert response.status_code == 400
    assert "too large" in response.json()["detail"]


def test_upload_uses_generated_file_name(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    video = tmp_path / "source.avi"
    make_video(video)
    response = client.post(
        "/api/inspection/upload-video",
        files={"file": ("../../evil name.avi", video.read_bytes(), "video/x-msvideo")},
    )
    assert response.status_code == 201
    assert response.json()["videoName"] == "evil name.avi"
    stored = list((tmp_path / "videos").glob("*"))
    assert len(stored) == 1 and stored[0].name != "evil name.avi"


def test_processing_without_model_returns_clear_error(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(config, "YOLO_MODEL_PATH", tmp_path / "missing.pt")
    video = tmp_path / "source.avi"
    make_video(video)
    inspection_id = client.post("/api/inspection/upload-video", files={"file": ("a.avi", video.read_bytes(), "video/x-msvideo")}).json()["id"]

    response = client.post("/api/inspection/process-video", json={"inspectionId": inspection_id})
    assert response.status_code == 503
    assert "Number plate detection model is not configured" in response.json()["detail"]


def test_unknown_inspection_id(client):
    assert client.get("/api/inspection/results/abc").status_code == 404
    assert client.post("/api/inspection/process-video", json={"inspectionId": "abc"}).status_code == 404


def test_manual_correction(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    client.post(ASSETS, json=asset_payload(assetId="GJ01AB1234", serialNumber="SN-9"))
    video = tmp_path / "source.avi"
    make_video(video)
    inspection_id = client.post("/api/inspection/upload-video", files={"file": ("a.avi", video.read_bytes(), "video/x-msvideo")}).json()["id"]
    # a video that is still only "UPLOADED" can't be corrected yet
    assert client.patch(f"/api/inspection/results/{inspection_id}", json={"plateNumber": "GJ01AB1234"}).status_code == 400
