"""CNG hydrotest verification.

Flow:  plate -> vehicle provider (fuel type etc.) -> cylinder test records in MongoDB
       -> status per cylinder -> overall status (the worst cylinder decides).

If the vehicle source does not know the plate (the demo/mock source only knows 6 fictional vehicles),
the app's OWN data is used before giving up: cylinder test records, then the asset register.
"VEHICLE_NOT_FOUND" is only returned when none of them knows the plate.

Rules for one cylinder (latest test record of that cylinder):
  result is Fail                         -> FAILED
  next-due date before today             -> EXPIRED
  next-due date within DUE_SOON_DAYS     -> DUE_SOON
  otherwise                              -> VALID
The next-due date is the record's own, or test date + CNG_TEST_VALIDITY_YEARS.
"""
import logging
from datetime import date, timedelta

import cv2
import numpy as np

from app import config
from app.errors import BadRequest, UpstreamError
from app.models.cng import SEVERITY_ORDER, CngStatus
from app.models.hydrotest import HydrotestStatus
from app.schemas.cng import CylinderTestCreate
from app.services import number_plate_service
from app.services.vehicle_provider import VehicleDetails, get_provider
from app.utils.date_utils import to_date, to_datetime, utc_now
from app.utils.plate_utils import looks_like_plate, normalize_plate, ocr_alternatives, plate_variants

logger = logging.getLogger(__name__)
COLLECTION = "cylinder_tests"


# ---------- pure rules (no database) ----------

def add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:  # 29 February -> 28 February
        return value.replace(year=value.year + years, day=28)


def cylinder_due_date(test: dict) -> date:
    explicit = to_date(test.get("nextDueDate"))
    return explicit or add_years(to_date(test["testDate"]), config.CNG_TEST_VALIDITY_YEARS)


def decide_cylinder_status(test: dict, today: date | None = None) -> CngStatus:
    today = today or date.today()
    if test["result"] == "Fail":
        return CngStatus.FAILED
    due = cylinder_due_date(test)
    if due < today:
        return CngStatus.EXPIRED
    if due <= today + timedelta(days=config.DUE_SOON_DAYS):
        return CngStatus.DUE_SOON
    return CngStatus.VALID


def worst_status(statuses: list[CngStatus]) -> CngStatus:
    for candidate in SEVERITY_ORDER:
        if candidate in statuses:
            return candidate
    return CngStatus.VALID


def _mask_name(name: str | None) -> str | None:
    """The owner's name is personal data: show initials only."""
    if not name:
        return None
    return " ".join(part[0] + "*" * (len(part) - 1) for part in name.split())


# ---------- cylinder test records ----------

def _test_to_dict(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "vehicleNumber": doc["vehicleNumber"],
        "cylinderSerial": doc["cylinderSerial"],
        "manufactureDate": to_date(doc.get("manufactureDate")),
        "testDate": to_date(doc["testDate"]),
        "nextDueDate": to_date(doc.get("nextDueDate")),
        "result": doc["result"],
        "testCenter": doc.get("testCenter"),
        "reportNumber": doc.get("reportNumber"),
        "createdAt": doc["createdAt"],
    }


def create_test(db, data: CylinderTestCreate) -> dict:
    doc = {
        "vehicleNumber": data.vehicleNumber,
        "cylinderSerial": data.cylinderSerial,
        "manufactureDate": to_datetime(data.manufactureDate),
        "testDate": to_datetime(data.testDate),
        "nextDueDate": to_datetime(data.nextDueDate),
        "result": data.result,
        "testCenter": data.testCenter,
        "reportNumber": data.reportNumber,
        "createdAt": utc_now(),
    }
    doc["_id"] = db[COLLECTION].insert_one(doc).inserted_id
    return _test_to_dict(doc)


def list_tests(db, vehicle_number: str | None = None) -> list[dict]:
    query = {"vehicleNumber": normalize_plate(vehicle_number)} if vehicle_number else {}
    return [_test_to_dict(d) for d in db[COLLECTION].find(query).sort("testDate", -1)]


# ---------- verification ----------

def _vehicle_out(vehicle: VehicleDetails) -> dict:
    return {
        "registrationNumber": vehicle.registration_number,
        "fuelType": vehicle.fuel_type,
        "ownerName": _mask_name(vehicle.owner_name),
        "vehicleClass": vehicle.vehicle_class,
        "makerModel": vehicle.maker_model,
        "registrationDate": vehicle.registration_date,
        "fitnessValidUpto": vehicle.fitness_valid_upto,
        "source": vehicle.source,
    }


def _latest_per_cylinder(db, plates) -> list[dict]:
    if isinstance(plates, str):
        plates = [plates]
    latest = {}
    for doc in db[COLLECTION].find({"vehicleNumber": {"$in": list(plates)}}).sort("testDate", -1):
        latest.setdefault(doc["cylinderSerial"], doc)  # newest first, so first one wins
    return list(latest.values())


def _result(plate, status, message, vehicle=None, cylinders=None) -> dict:
    return {
        "plateNumber": plate,
        "status": status,
        "message": message,
        "vehicle": _vehicle_out(vehicle) if vehicle else None,
        "cylinders": cylinders or [],
        "checkedAt": utc_now(),
    }


def _cylinder_rows(tests: list[dict], today: date) -> list[dict]:
    rows = []
    for test in tests:
        due = cylinder_due_date(test)
        rows.append({
            "cylinderSerial": test["cylinderSerial"],
            "manufactureDate": to_date(test.get("manufactureDate")),
            "lastTestDate": to_date(test["testDate"]),
            "nextDueDate": due,
            "daysToDue": (due - today).days,
            "result": test["result"],
            "testCenter": test.get("testCenter"),
            "reportNumber": test.get("reportNumber"),
            "status": decide_cylinder_status(test, today),
        })
    return rows


def _status_result(plate, rows, vehicle) -> dict:
    overall = worst_status([c["status"] for c in rows])
    messages = {
        CngStatus.VALID: "CNG cylinder hydrotest is valid.",
        CngStatus.DUE_SOON: f"Hydrotest is valid, but a re-test is due within {config.DUE_SOON_DAYS} days.",
        CngStatus.EXPIRED: "Hydrotest has expired for at least one cylinder. A re-test is required.",
        CngStatus.FAILED: "At least one cylinder failed its latest hydrotest.",
    }
    return _result(plate, overall, messages[overall], vehicle, rows)


# asset-register status -> the status names this screen uses
_ASSET_TO_CNG = {
    HydrotestStatus.VALID: CngStatus.VALID,
    HydrotestStatus.DUE_SOON: CngStatus.DUE_SOON,
    HydrotestStatus.OVERDUE: CngStatus.EXPIRED,
    HydrotestStatus.FAILED: CngStatus.FAILED,
    HydrotestStatus.PENDING: CngStatus.NO_RECORD,
}


def _asset_fallback(db, plates: list[str], today: date) -> dict | None:
    """The plate is not a known vehicle, but it may be an asset in the asset register (e.g. a tanker truck)."""
    from app.services import asset_service, hydrotest_service
    from app.services.hydrotest_status_service import decide_status

    asset = None
    for spelling in plates:
        asset = asset_service.find_by_identifier(db, spelling)
        if asset:
            break
    if asset is None:
        return None

    latest = hydrotest_service.latest_record(db, asset["assetId"])
    asset_status = decide_status(asset, latest, today)
    status = _ASSET_TO_CNG.get(asset_status, CngStatus.NO_RECORD)

    vehicle = VehicleDetails(
        registration_number=asset["assetId"], fuel_type=None, vehicle_class=asset.get("assetType"),
        maker_model=f"{asset.get('assetType', '')} at {asset.get('station', '')}".strip(), source="asset register",
    )
    last_test = to_date(asset.get("testDate")) or (to_date(latest.get("testDate")) if latest else None)
    due = to_date(asset.get("nextDueDate")) or (to_date(latest.get("nextDueDate")) if latest else None)
    rows = []
    if last_test and due:
        rows.append({
            "cylinderSerial": asset.get("serialNumber") or asset["assetId"],
            "manufactureDate": None,
            "lastTestDate": last_test,
            "nextDueDate": due,
            "daysToDue": (due - today).days,
            "result": latest["result"].value if latest and hasattr(latest["result"], "value") else (latest["result"] if latest else "Pass"),
            "testCenter": latest.get("performedBy") if latest else None,
            "reportNumber": None,
            "status": status if status != CngStatus.NO_RECORD else CngStatus.VALID,
        })
    messages = {
        CngStatus.VALID: "Found in the asset register. Hydrotest is valid.",
        CngStatus.DUE_SOON: f"Found in the asset register. Hydrotest is valid, but a re-test is due within {config.DUE_SOON_DAYS} days.",
        CngStatus.EXPIRED: "Found in the asset register. Hydrotest is overdue. A re-test is required.",
        CngStatus.FAILED: "Found in the asset register. The latest hydrotest failed.",
        CngStatus.NO_RECORD: "Found in the asset register, but there is no hydrotest date on file yet.",
    }
    return _result(asset["assetId"], status, messages[status], vehicle, rows if status != CngStatus.NO_RECORD else [])


def verify(db, plate_text: str, provider=None, today: date | None = None) -> dict:
    plate = normalize_plate(plate_text)
    if len(plate) < 4:
        raise BadRequest("Please enter a valid vehicle registration number.")
    today = today or date.today()
    spellings = plate_variants(plate)  # GJ1AB1234 and GJ01AB1234 are the same vehicle

    vehicle = None
    provider_error = None
    for spelling in spellings:
        try:
            vehicle = (provider or get_provider()).fetch(spelling)
        except UpstreamError as error:
            provider_error = error
            break
        if vehicle is not None:
            plate = spelling
            break

    tests = _latest_per_cylinder(db, spellings)

    if vehicle is None and tests:
        # The vehicle source does not know this plate, but we hold cylinder test records for it.
        # Such records only exist for CNG vehicles, so it is treated as CNG (and labelled as such).
        plate = tests[0]["vehicleNumber"]
        vehicle = VehicleDetails(plate, "CNG", source="cylinder test records")

    if vehicle is None:
        fallback = _asset_fallback(db, spellings, today)
        if fallback is not None:
            return fallback
        if provider_error is not None:
            raise provider_error
        hint = " (the demo vehicle source only knows a few sample vehicles)" if config.VEHICLE_PROVIDER == "mock" else ""
        return _result(
            plate, CngStatus.VEHICLE_NOT_FOUND,
            f"No vehicle, cylinder record or asset was found for {plate}{hint}. "
            "Check the number, or add a cylinder test record / asset for it.",
        )

    if vehicle.fuel_type is None:
        # never guess: "unknown fuel" must not be reported as "not CNG"
        raise UpstreamError("The vehicle information service did not return the fuel type, so CNG status cannot be checked.")
    if not vehicle.is_cng:
        return _result(
            plate, CngStatus.NOT_CNG,
            f"This vehicle runs on {vehicle.fuel_type}, not CNG. The CNG hydrotest check does not apply.", vehicle,
        )

    if not tests:
        tests = _latest_per_cylinder(db, spellings)
    if not tests:
        return _result(plate, CngStatus.NO_RECORD, "This is a CNG vehicle but no cylinder hydrotest record was found.", vehicle)

    return _status_result(plate, _cylinder_rows(tests, today), vehicle)


def _known_plates(db, candidates: list[str]) -> list[str]:
    """Which of these spellings exist in our own records (cylinder tests or asset register)?"""
    if not candidates:
        return []
    found = set(db[COLLECTION].distinct("vehicleNumber", {"vehicleNumber": {"$in": candidates}}))
    found |= set(db["assets"].distinct("assetId", {"assetId": {"$in": candidates}}))
    found |= set(db["assets"].distinct("serialNumber", {"serialNumber": {"$in": candidates}}))
    return sorted(found)


# ---------- camera / image scan ----------

def scan_image(db, data: bytes) -> dict:
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise BadRequest("The image could not be read. Please send a JPG, PNG or WebP photo.")

    number_plate_service.get_model()
    number_plate_service.check_ocr_available()

    try:
        reading = number_plate_service.find_plate_in_frame(frame)
    except number_plate_service.NoPlateFound as error:
        return {"plateDetected": False, "message": str(error)}

    low_confidence = reading.ocr_confidence < config.OCR_MIN_CONFIDENCE
    response = {
        "plateDetected": True,
        "plateNumber": reading.text,
        "ocrConfidence": round(reading.ocr_confidence, 3),
        "detectionConfidence": round(reading.detection_confidence, 3),
        "lowConfidence": low_confidence,
        "plateFormatValid": looks_like_plate(reading.text),
        "message": "OCR confidence is low. Please check the number and correct it if needed." if low_confidence else None,
        "verification": None,
    }
    try:
        verification = verify(db, reading.text)

        # OCR mixes up look-alike characters (O/0, B/8, S/5...). When the exact reading matches nothing,
        # accept a corrected spelling ONLY if exactly one existing record matches it.
        if verification["status"] == CngStatus.VEHICLE_NOT_FOUND:
            matches = _known_plates(db, ocr_alternatives(reading.text))
            if len(matches) == 1:
                corrected = verify(db, matches[0])
                if corrected["status"] != CngStatus.VEHICLE_NOT_FOUND:
                    response["plateCorrectedFrom"] = reading.text
                    response["plateNumber"] = corrected["plateNumber"]
                    response["message"] = (
                        f"Read as {reading.text}; matched the registered vehicle {corrected['plateNumber']}. Please confirm."
                    )
                    verification = corrected
        response["verification"] = verification
    except UpstreamError as error:
        # keep the plate we read; only the lookup failed
        response["message"] = error.message
    return response