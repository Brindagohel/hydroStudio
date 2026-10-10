from enum import Enum


class CngStatus(str, Enum):
    VALID = "VALID"                          # every cylinder's hydrotest is in date
    DUE_SOON = "DUE_SOON"                    # valid, but a re-test is due within DUE_SOON_DAYS
    EXPIRED = "EXPIRED"                      # a cylinder's re-test date has passed
    FAILED = "FAILED"                        # a cylinder's latest hydrotest failed
    NO_RECORD = "NO_RECORD"                  # CNG vehicle, but no hydrotest record on file
    NOT_CNG = "NOT_CNG"                      # vehicle is not CNG, check does not apply
    VEHICLE_NOT_FOUND = "VEHICLE_NOT_FOUND"  # the vehicle source has no such registration # the vehicle source has no such registration


# worst first: the overall status of a vehicle is the worst status of its cylinders
SEVERITY_ORDER = [CngStatus.FAILED, CngStatus.EXPIRED, CngStatus.DUE_SOON, CngStatus.VALID]
