"""The one place that decides a hydrotest status.

Rules, checked in this order:
  no asset                         -> NOT_FOUND
  latest test result is Fail       -> FAILED
  latest test result is Pending    -> PENDING
  no next-due date available       -> PENDING
  next-due date before today       -> OVERDUE
  next-due date within DUE_SOON_DAYS (today included) -> DUE_SOON
  anything else                    -> VALID

The next-due date comes from the asset (the register's validity date). If the
asset has none, the latest test's own next-due date is used. "Today" is the
server's local date.
"""
from datetime import date, timedelta

from app import config
from app.models.hydrotest import HydrotestStatus, TestResult
from app.utils.date_utils import to_date


def decide_status(asset: dict | None, latest_test: dict | None, today: date | None = None) -> HydrotestStatus:
    if asset is None:
        return HydrotestStatus.NOT_FOUND

    today = today or date.today()

    if latest_test is not None:
        if latest_test["result"] == TestResult.FAIL:
            return HydrotestStatus.FAILED
        if latest_test["result"] == TestResult.PENDING:
            return HydrotestStatus.PENDING

    next_due = to_date(asset.get("nextDueDate"))
    if next_due is None and latest_test is not None:
        next_due = to_date(latest_test.get("nextDueDate"))
    if next_due is None:
        return HydrotestStatus.PENDING

    if next_due < today:
        return HydrotestStatus.OVERDUE
    if next_due <= today + timedelta(days=config.DUE_SOON_DAYS):
        return HydrotestStatus.DUE_SOON
    return HydrotestStatus.VALID
