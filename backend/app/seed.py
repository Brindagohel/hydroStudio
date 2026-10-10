"""Fills MongoDB with fictional demo data.  Run from the backend folder:

    python -m app.seed

WARNING: this empties the assets, hydrotests and inspection_results
collections of the database named in DATABASE_NAME before inserting.
Dates are worked out from today, so every status shows up whenever you run it.
"""
from datetime import date, timedelta

from app.database.connection import create_indexes, get_database
from app.schemas.asset import AssetCreate
from app.schemas.hydrotest import HydrotestCreate
from app.schemas.cng import CylinderTestCreate
from app.services import asset_service, cng_service, hydrotest_service

ASSETS = [
    ("GJ01AB1234", "Demo Station A", "Tanker Truck", "DEMO-TT-001"),
    ("GJ01CD5678", "Demo Station A", "Tanker Truck", "DEMO-TT-002"),
    ("GJ05EF4321", "Demo Station B", "Tanker Truck", "DEMO-TT-003"),
    ("GJ05GH8765", "Demo Station B", "Tanker Truck", "DEMO-TT-004"),
    ("DEMO-TANK-001", "Demo Station A", "Storage Tank", "DEMO-ST-001"),
    ("DEMO-TANK-002", "Demo Station C", "Storage Tank", "DEMO-ST-002"),
    ("DEMO-VESSEL-001", "Demo Station C", "Pressure Vessel", "DEMO-PV-001"),
    ("DEMO-VESSEL-002", "Demo Station C", "Pressure Vessel", "DEMO-PV-002"),
    ("DEMO-HOSE-001", "Demo Station B", "Hose Assembly", "DEMO-HA-001"),
    ("DEMO-HOSE-002", "Demo Station A", "Hose Assembly", "DEMO-HA-002"),
]

# (asset, days ago the test was done, result, days from test until next due, provider, notes)
RECORDS = [
    ("GJ01AB1234", 565, "Pass", 365, "Demo Inspector 1", "Annual test, no leaks"),
    ("GJ01AB1234", 200, "Pass", 365, "Demo Inspector 1", "Held 30 minutes at test pressure"),  # VALID
    ("GJ01CD5678", 350, "Pass", 365, "Demo Inspector 2", "Minor paint damage noted"),  # DUE SOON
    ("GJ05EF4321", 765, "Pass", 365, "Demo Inspector 2", "Annual test, no leaks"),
    ("GJ05EF4321", 400, "Pass", 365, "Demo Inspector 3", "Passed, retest due"),  # OVERDUE
    ("GJ05GH8765", 380, "Pass", 365, "Demo Inspector 1", "Annual test, no leaks"),
    ("GJ05GH8765", 20, "Fail", None, "Demo Inspector 3", "Pressure dropped at rear valve"),  # FAILED
    ("DEMO-TANK-001", 90, "Pass", 365, "Demo Inspector 2", "Passed with no findings"),  # VALID
    ("DEMO-TANK-002", 3, "Pending", None, "Demo Inspector 3", "Waiting for test equipment"),  # PENDING
    ("DEMO-VESSEL-001", 340, "Pass", 365, "Demo Inspector 1", "Gauge replaced before test"),  # DUE SOON
    ("DEMO-VESSEL-002", 500, "Pass", 365, "Demo Inspector 2", "Passed, retest due"),  # OVERDUE
    ("DEMO-HOSE-001", 30, "Pass", 365, "Demo Inspector 3", "Passed with no findings"),  # VALID
    ("DEMO-HOSE-002", 5, "Fail", None, "Demo Inspector 1", "Hose wall bulged under pressure"),  # FAILED
]


# CNG demo: (vehicle, cylinder serial, cylinder age in years, days until re-test is due, result)
# "due_in_days" is when the next re-test falls due, so every status appears whenever you seed.
CYLINDERS = [
    ("GJ01AB1001", "CYL-1001", 4, 400, "Pass"),    # VALID
    ("GJ01CD2002", "CYL-2002", 6, 15, "Pass"),     # DUE_SOON (due in 15 days)
    ("GJ05EF3003", "CYL-3003", 8, -40, "Pass"),    # EXPIRED (due 40 days ago)
    ("GJ05GH4004", "CYL-4004", 3, 300, "Pass"),    # bus, cylinder 1: valid
    ("GJ05GH4004", "CYL-4005", 3, -5, "Fail"),     # bus, cylinder 2: failed -> overall FAILED
    # GJ05JK5005 (CNG, no records) -> NO_RECORD;  GJ06LM6006 (petrol) -> NOT_CNG
]


def seed_cylinders(db, today: date) -> None:
    years = cng_service.config.CNG_TEST_VALIDITY_YEARS
    for plate, serial, mfg_years_ago, due_in_days, result in CYLINDERS:
        due = today + timedelta(days=due_in_days)
        test_date = cng_service.add_years(due, -years)
        cng_service.create_test(
            db,
            CylinderTestCreate(
                vehicleNumber=plate,
                cylinderSerial=serial,
                manufactureDate=cng_service.add_years(test_date, -mfg_years_ago),
                testDate=test_date,
                nextDueDate=due,
                result=result,
                testCenter="Demo Test Centre",
                reportNumber=f"DEMO-CNG-{serial}",
            ),
        )


def run() -> None:
    db = get_database()
    for name in ("assets", "hydrotests", "inspection_results", "cylinder_tests"):
        db[name].delete_many({})
    create_indexes(db)

    for asset_id, station, asset_type, serial in ASSETS:
        asset_service.create_asset(
            db, AssetCreate(assetId=asset_id, station=station, assetType=asset_type, serialNumber=serial)
        )

    today = date.today()
    for number, (asset_id, days_ago, result, valid_days, provider, notes) in enumerate(RECORDS, start=1):
        test_date = today - timedelta(days=days_ago)
        next_due = test_date + timedelta(days=valid_days) if valid_days else None
        hydrotest_service.create_record(
            db,
            HydrotestCreate(
                assetId=asset_id,
                testDate=test_date,
                performedBy=provider,
                result=result,
                notes=notes,
                reportFile=f"demo-report-{number:03d}.pdf" if result != "Pending" else None,
                nextDueDate=next_due,
            ),
        )

    seed_cylinders(db, today)
    print(f"Inserted {len(ASSETS)} demo assets, {len(RECORDS)} demo hydrotest records and demo CNG cylinder tests.")


if __name__ == "__main__":
    run()
