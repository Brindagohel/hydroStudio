# Hydrotesting Management & Inspection Workflow


## CNG Hydrotest Verification (camera -> vehicle lookup -> hydrotest check)

Open **CNG Verify** in the app. Flow:

1. **Camera**: the browser camera (`getUserMedia`) captures a frame every ~2.5 s (or on "Capture & Check", or "Upload Photo" on a phone). Camera access needs **HTTPS or localhost**.
2. **Plate**: backend `POST /api/cng/scan` runs YOLO detection, OpenCV preprocessing and Tesseract OCR on the frame.
3. **Vehicle details**: the plate is looked up through a *vehicle provider* (`VEHICLE_PROVIDER` in `backend/.env`).
4. **Hydrotest check**: if the vehicle is CNG, its cylinders' latest test records decide the status.

| Status | Meaning |
|---|---|
| VALID | every cylinder's hydrotest is in date |
| DUE_SOON | valid, but a re-test is due within `DUE_SOON_DAYS` |
| EXPIRED | a cylinder's re-test date has passed |
| FAILED | a cylinder's latest hydrotest failed (beats everything else) |
| NO_RECORD | CNG vehicle, but no test record on file |
| NOT_CNG | vehicle is not CNG (dual-fuel such as PETROL/CNG counts as CNG) |
| VEHICLE_NOT_FOUND | the vehicle source has no such registration |

If the vehicle service is down, or does not return a fuel type, the API answers with an error (502) instead of guessing.

### Connecting a real government / RC data source
`VEHICLE_PROVIDER=mock` (default) uses fictional demo vehicles. For real data set `VEHICLE_PROVIDER=http`, `VEHICLE_API_URL` (must contain `{plate}`), `VEHICLE_API_KEY` and `VEHICLE_API_KEY_HEADER`, then adapt `HttpVehicleProvider.map_response` in `backend/app/services/vehicle_provider.py` to your provider's JSON.
There is no open public Vahan/Parivahan API: you need an authorised channel or a licensed RC-verification provider, and you must follow its terms and privacy rules. The owner's name is masked to initials in API responses.

### Cylinder test records and the validity rule
Records are added with `POST /api/cng/cylinder-tests` (see `/docs`). A record's own `nextDueDate` is used if given; otherwise `testDate + CNG_TEST_VALIDITY_YEARS` (default 3). **Confirm the correct interval with PESO / your regulator before relying on the default.**
`python -m app.seed` loads demo vehicles that show every status: GJ01AB1001 (valid), GJ01CD2002 (due soon), GJ05EF3003 (expired), GJ05GH4004 (one cylinder failed), GJ05JK5005 (no record), GJ06LM6006 (petrol).

Still required for plate detection: your own trained YOLO weights at `models/number_plate_model.pt`, and Tesseract installed.

## 1. Project Overview

A small internal-style web application for tracking hydrotests of assets
(tankers, tanks, pressure vessels, hoses), plus a computer-vision workflow:
upload an inspection video, detect and read the number plate, and see the
hydrotest status of the matching asset.

**All data is fictional demo data.** The project never touches any FuelFlux
system, credential or customer information.

## 2. Features

- Asset register: create, list, view, update (asset ID is unique and immutable)
- Hydrotest records (Pass / Fail / Pending) with report file name and notes
- Status worked out by one backend function: VALID, DUE_SOON, OVERDUE, FAILED, PENDING, NOT_FOUND
- Dashboard with live counts and a "needs attention" list
- Filter by station, asset type, status and due-date range; search; sort by next-due date
- Video inspection: frame sampling, YOLO plate detection, OpenCV preprocessing, OCR, asset lookup, manual correction
- Validation, duplicate handling (HTTP 409), readable error messages, upload safety checks
- Automated tests and Swagger docs at `/docs`

## 3. Technology Stack

Backend: Python, FastAPI, PyMongo, Pydantic, OpenCV, Ultralytics YOLO, Tesseract OCR (pytesseract).
Frontend: React (Vite), JavaScript, Axios, plain CSS. Database: MongoDB.

## 4. Architecture

```
React Frontend
      |  HTTP / JSON
      v
FastAPI Backend ---------------+
      |                        |
      v                        v
   MongoDB               Computer Vision
                         OpenCV + YOLO
                               |
                              OCR
                               |
                          Plate number
                               |
                               v
                          Asset lookup
                               |
                               v
                       Hydrotest status
```

Routes only handle HTTP. Business logic lives in `services/`. The status rules
are in a single function, `decide_status()` in `hydrotest_status_service.py`;
React only displays what the API returns.

## 5. Project Structure

```
backend/
  app/
    main.py                 FastAPI app, error handlers
    config.py               settings from environment variables
    errors.py               small exception classes -> HTTP codes
    seed.py                 demo data
    api/routes/             assets.py, hydrotests.py, dashboard.py, inspection.py
    models/                 enums + MongoDB document -> dict helpers
    schemas/                Pydantic request/response models
    services/               asset, hydrotest, status, inspection, number_plate
    database/connection.py  MongoDB client + indexes
    utils/                  date_utils.py, plate_utils.py
  tests/                    pytest tests
  make_demo_video.py        creates a fictional plate video
  requirements.txt, requirements-dev.txt, .env.example
frontend/src/               pages/, components/, services/api.js, utils/
models/                     put number_plate_model.pt here
uploads/                    uploaded videos and plate crops (not committed)
```

## 6. Prerequisites

Python 3.10+, Node.js 18+, MongoDB 6+, Tesseract OCR.

## 7. MongoDB Setup

Install MongoDB Community Edition and start it, or use Docker:

```
docker run -d --name hydrotest-mongo -p 27017:27017 mongo:7
```

Collections (created automatically): `assets`, `hydrotests`, `inspection_results`.
Indexes: unique `assetId`, unique `serialNumber`, (`station`, `assetType`), `nextDueDate`, (`assetId`, `testDate`).

## 8. Backend Setup

```
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
```

## 9. Frontend Setup

```
cd frontend
npm install
```

## 10. Environment Variables (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| MONGODB_URL | mongodb://localhost:27017 | MongoDB connection |
| DATABASE_NAME | hydrotest_db | Database name |
| YOLO_MODEL_PATH | models/number_plate_model.pt | YOLO weights (relative to project root) |
| YOLO_CONFIDENCE | 0.40 | Minimum detection confidence |
| FRAME_SKIP | 5 | Run YOLO on every Nth frame |
| OCR_MIN_CONFIDENCE | 0.60 | Below this the UI warns the user to check the number |
| UPLOAD_DIR | uploads | Where videos and plate crops are stored |
| MAX_UPLOAD_MB | 100 | Upload size limit |
| DUE_SOON_DAYS | 30 | "Due soon" window |
| TEST_VALIDITY_DAYS | 365 | Default validity of a passed test |
| CORS_ORIGINS | http://localhost:5173 | Allowed frontend origins |

`.env` is git-ignored; only `.env.example` is committed.

## 11. Seed Data

```
cd backend
python -m app.seed
```

Inserts 10 fictional assets and 13 hydrotest records (Pass, Fail, Pending, due soon, overdue)
across Demo Station A/B/C. Dates are relative to today. **It empties the three collections first.**
Demo plates: `GJ01AB1234` (valid), `GJ01CD5678` (due soon), `GJ05EF4321` (overdue), `GJ05GH8765` (failed).

## 12. Running the Application

```
# terminal 1 - backend (from backend/)
uvicorn app.main:app --reload --port 8000

# terminal 2 - frontend (from frontend/)
npm run dev
```

Open http://localhost:5173. API docs: http://localhost:8000/docs.

## 13. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | /api/hydrotests/assets | Create asset (409 on duplicate) |
| GET | /api/hydrotests/assets | List: `station`, `asset_type`, `status`, `due_from`, `due_to`, `search`, `sort_by`, `sort_order` |
| GET | /api/hydrotests/assets/options | Stations / types for filters |
| GET | /api/hydrotests/assets/{assetId} | One asset |
| PATCH | /api/hydrotests/assets/{assetId} | Update asset |
| POST | /api/hydrotests/records | Create hydrotest record |
| GET | /api/hydrotests/records | List records (`asset_id`, `result`) |
| GET | /api/hydrotests/records/{id} | One record |
| PATCH | /api/hydrotests/records/{id} | Update record |
| GET | /api/hydrotests/summary | Dashboard data |
| POST | /api/inspection/upload-video | Upload video (multipart `file`) |
| POST | /api/inspection/process-video | Start processing `{"inspectionId": "..."}` (202) |
| GET | /api/inspection/results/{id} | Progress / result (poll this) |
| PATCH | /api/inspection/results/{id} | Manual correction `{"plateNumber": "..."}` |
| GET | /api/inspection/results/{id}/plate-image | Cropped plate JPEG |
| GET | /api/inspection/assets/{plate_number} | Asset + status for a plate |

The inspection upload and process steps are separate so the browser can show upload and
processing states, and processing runs in a background task with progress polling.

Example requests:

```
curl -X POST localhost:8000/api/hydrotests/assets -H "Content-Type: application/json" \
  -d '{"assetId":"GJ01AB9999","station":"Demo Station A","assetType":"Tanker Truck","serialNumber":"DEMO-TT-099"}'

curl "localhost:8000/api/hydrotests/assets?station=Demo%20Station%20A&status=OVERDUE&sort_order=desc"

curl -X POST localhost:8000/api/hydrotests/records -H "Content-Type: application/json" \
  -d '{"assetId":"GJ01AB9999","testDate":"2026-03-10","performedBy":"Demo Inspector","result":"Pass","reportFile":"demo-report-020.pdf"}'

curl localhost:8000/api/inspection/assets/gj-01-ab-1234
```

## 14. Video Inspection Workflow

1. Upload: extension (.mp4/.avi/.mov/.mkv), MIME type, size and "OpenCV can read a frame" are checked. The file is stored under a generated name.
2. Processing (background task): OpenCV reads the video and runs YOLO on every `FRAME_SKIP`-th frame only.
3. The three most confident detections are cropped (with a little padding).
4. Each crop gets several OpenCV versions: grayscale + resize, denoise, Otsu threshold, adaptive threshold, sharpen.
5. Tesseract OCR runs on each version; the text is normalized (`" gj-01 ab 1234 "` -> `GJ01AB1234`). Letters and digits are never swapped.
6. The best result wins (a result matching the plate pattern beats a higher-confidence one that does not).
7. MongoDB is searched by asset ID or serial number, the latest hydrotest is loaded and `decide_status()` gives the status.
8. The result is saved in `inspection_results` and shown in the UI. Low OCR confidence shows a warning; the user can correct the number and search again.

If no plate is found the UI shows the "No number plate could be detected..." message and a manual entry box.

## 15. YOLO Model Setup

The weights file is not included (size and licence). Place a YOLO licence-plate detector at
`models/number_plate_model.pt` (see `models/README.md`). Without it, **Upload & Analyze**
shows "Number plate detection model is not configured." Nothing is faked; all other
pages work normally. To try the flow: `python make_demo_video.py` writes a fictional plate video to
`uploads/`, though a real clip is better for a real model.

## 16. OCR Setup

Install the Tesseract engine (the Python package only calls it):

- Ubuntu/Debian: `sudo apt install tesseract-ocr`
- macOS: `brew install tesseract`
- Windows: install from the UB Mannheim builds and add it to PATH

If it is missing the API answers with a clear 503 message.

## 17. Testing

```
cd backend
pytest
```

Tests use an in-memory MongoDB (mongomock), so no database is needed. They cover asset create/duplicate/invalid
data, hydrotest create/invalid dates, dashboard counts, due-soon/overdue/failed/pending logic, plate
normalization, not-found handling, upload validation, and the frame sampling + preprocessing + OCR
code (using a stand-in for the YOLO model so no weights are needed; skipped if Tesseract is missing).

## 18. Assumptions

- **Duplicates:** `assetId` and `serialNumber` must each be unique. A duplicate returns 409 and nothing is overwritten. IDs and serials are stored upper-case.
- **Status is derived,** not entered. The asset's next-due date decides VALID / DUE_SOON / OVERDUE; the latest record's Fail or Pending overrides it. An asset with no records is judged by its own dates, or PENDING if it has none.
- A new or edited hydrotest copies its test date and next-due date to the asset. A passed test with no next-due date gets +365 days.
- "Due soon" = due today up to 30 days ahead. "Overdue" = due date before today.
- **Dates:** plain calendar dates, "today" is the server's local date. They are stored as midnight datetimes in MongoDB.
- The number plate is the asset ID (or serial number) of the asset.
- Pass/Fail test dates are not checked against the future; Pending may be any date.

## 19. Limitations

- Needs a YOLO plate model supplied by you; accuracy depends on it and on video quality.
- OCR reads single-line plates (`--psm 7`); two-line plates may fail. It is Tesseract, not a plate-specific OCR.
- Statuses are calculated in Python for each list request; fine for hundreds of assets, not for millions.
- Background processing runs inside the API process (no job queue); results are kept in MongoDB, so a server restart mid-processing leaves that inspection stuck at PROCESSING.
- No login or roles. Report files are only names, not uploads. No delete endpoints.
- The frontend has no automated tests.

## 20. Future Improvements

Authentication, report PDF upload, pagination, a job queue for video processing, a plate-specific OCR model,
two-line plate support, record deletion with audit trail, frontend tests.

## 21. AI Tool Disclosure

AI coding assistance was used during development of this project. The submitted code was reviewed, tested,
modified and understood by the candidate.
