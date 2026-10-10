from datetime import date, datetime, timezone


def to_datetime(value: date | None) -> datetime | None:
    """MongoDB can store datetimes but not plain dates, so we save midnight."""
    if value is None:
        return None
    return datetime(value.year, value.month, value.day)


def to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check_due_after_test(test_date: date | None, next_due_date: date | None) -> None:
    if test_date and next_due_date and next_due_date < test_date:
        raise ValueError("Next due date cannot be earlier than the test date")
