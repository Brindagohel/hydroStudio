from datetime import date, timedelta

from app.models.hydrotest import HydrotestStatus as S
from app.services.hydrotest_status_service import decide_status

TODAY = date(2026, 6, 15)


def asset(days_until_due):
    return {"assetId": "A1", "nextDueDate": TODAY + timedelta(days=days_until_due) if days_until_due is not None else None}


def test_no_asset_is_not_found():
    assert decide_status(None, None, TODAY) == S.NOT_FOUND


def test_valid():
    assert decide_status(asset(120), {"result": "Pass"}, TODAY) == S.VALID


def test_due_soon_inside_30_days():
    assert decide_status(asset(29), {"result": "Pass"}, TODAY) == S.DUE_SOON


def test_due_today_and_day_30_are_due_soon():
    assert decide_status(asset(0), {"result": "Pass"}, TODAY) == S.DUE_SOON
    assert decide_status(asset(30), {"result": "Pass"}, TODAY) == S.DUE_SOON


def test_day_31_is_valid():
    assert decide_status(asset(31), {"result": "Pass"}, TODAY) == S.VALID


def test_overdue_yesterday():
    assert decide_status(asset(-1), {"result": "Pass"}, TODAY) == S.OVERDUE


def test_failed_beats_dates():
    assert decide_status(asset(200), {"result": "Fail"}, TODAY) == S.FAILED


def test_pending_beats_dates():
    assert decide_status(asset(-50), {"result": "Pending"}, TODAY) == S.PENDING


def test_no_dates_and_no_tests_is_pending():
    assert decide_status(asset(None), None, TODAY) == S.PENDING


def test_asset_dates_used_when_there_is_no_record():
    assert decide_status(asset(-3), None, TODAY) == S.OVERDUE
