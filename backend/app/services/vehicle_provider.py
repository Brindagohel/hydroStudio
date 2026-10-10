"""Where vehicle details (fuel type, class, owner...) come from.

Two providers share one interface, so the rest of the app never knows which is used:

  MockVehicleProvider  built-in fictional vehicles, for demos and tests (default)
  HttpVehicleProvider  calls a real vehicle-registration API (RC lookup)

Choose with VEHICLE_PROVIDER=mock|http in backend/.env.

IMPORTANT: there is no open public API for Vahan/Parivahan data. A real deployment needs an
authorised channel or a licensed third-party RC-verification provider. Every provider answers
with a different JSON shape, so `HttpVehicleProvider.map_response` is the one place to adapt
once you know which provider you use. It already tolerates the most common field names.
"""
import logging
from dataclasses import dataclass
from typing import Protocol

from app import config
from app.errors import ServiceUnavailable, UpstreamError

logger = logging.getLogger(__name__)


@dataclass
class VehicleDetails:
    registration_number: str
    fuel_type: str | None
    owner_name: str | None = None
    vehicle_class: str | None = None
    maker_model: str | None = None
    registration_date: str | None = None
    fitness_valid_upto: str | None = None
    source: str = "unknown"

    @property
    def is_cng(self) -> bool:
        # also matches dual-fuel entries such as "PETROL/CNG"
        return "CNG" in (self.fuel_type or "").upper()


class VehicleProvider(Protocol):
    def fetch(self, plate: str) -> VehicleDetails | None:
        """Return the vehicle, or None if the registration does not exist.
        Raise UpstreamError if the source could not be reached or answered badly."""


# ---------------------------------------------------------------- mock

def _demo(plate, fuel, owner, vclass, model, reg, fitness):
    return VehicleDetails(plate, fuel, owner, vclass, model, reg, fitness, source="mock (demo data)")


MOCK_VEHICLES = {
    v.registration_number: v
    for v in [
        _demo("GJ01AB1001", "CNG", "Demo Owner One", "Light Goods Vehicle", "Demo Motors Cargo CNG", "2022-06-15", "2028-06-14"),
        _demo("GJ01CD2002", "CNG", "Demo Owner Two", "Motor Car", "Demo Motors Sedan CNG", "2021-03-02", "2036-03-01"),
        _demo("GJ05EF3003", "PETROL/CNG", "Demo Owner Three", "Three Wheeler", "Demo Auto CNG", "2020-09-20", "2028-09-19"),
        _demo("GJ05GH4004", "CNG", "Demo Owner Four", "Bus", "Demo Bus CNG (2 cylinders)", "2019-01-11", "2027-01-10"),
        _demo("GJ05JK5005", "CNG", "Demo Owner Five", "Motor Car", "Demo Motors Hatch CNG", "2023-02-28", "2038-02-27"),
        _demo("GJ06LM6006", "PETROL", "Demo Owner Six", "Motor Car", "Demo Motors Hatch Petrol", "2022-12-01", "2037-11-30"),
    ]
}


class MockVehicleProvider:
    def fetch(self, plate: str) -> VehicleDetails | None:
        return MOCK_VEHICLES.get(plate)


# ---------------------------------------------------------------- real API

def _pick(data: dict, *names):
    for name in names:
        value = data.get(name)
        if value not in (None, ""):
            return str(value)
    return None


class HttpVehicleProvider:
    def fetch(self, plate: str) -> VehicleDetails | None:
        import httpx

        if "{plate}" not in config.VEHICLE_API_URL:
            raise ServiceUnavailable("VEHICLE_API_URL is not configured. It must contain {plate}.")
        url = config.VEHICLE_API_URL.replace("{plate}", plate)
        headers = {"Accept": "application/json"}
        if config.VEHICLE_API_KEY:
            headers[config.VEHICLE_API_KEY_HEADER] = config.VEHICLE_API_KEY

        try:
            response = httpx.get(url, headers=headers, timeout=config.VEHICLE_API_TIMEOUT)
        except httpx.HTTPError as error:
            logger.warning("Vehicle API request failed: %s", type(error).__name__)  # never log the URL/key
            raise UpstreamError("The vehicle information service could not be reached. Please try again.")

        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise UpstreamError("The vehicle information service rejected our credentials.")
        if response.status_code >= 400:
            raise UpstreamError(f"The vehicle information service returned an error ({response.status_code}).")

        try:
            payload = response.json()
        except ValueError:
            raise UpstreamError("The vehicle information service sent an unreadable response.")
        return self.map_response(payload, plate)

    @staticmethod
    def map_response(payload, plate: str) -> VehicleDetails | None:
        """ADAPT THIS to your provider's JSON. Unwraps {"data": {...}} / {"result": {...}}."""
        if not isinstance(payload, dict):
            raise UpstreamError("The vehicle information service sent an unexpected response.")
        for wrapper in ("data", "result"):
            if isinstance(payload.get(wrapper), dict):
                payload = payload[wrapper]
                break
        if not payload:
            return None
        return VehicleDetails(
            registration_number=plate,
            fuel_type=_pick(payload, "fuel_type", "fuelType", "fuel", "fuel_descr", "fuel_desc"),
            owner_name=_pick(payload, "owner_name", "ownerName", "owner"),
            vehicle_class=_pick(payload, "vehicle_class", "vehicleClass", "class", "vehicle_class_desc"),
            maker_model=_pick(payload, "maker_model", "makerModel", "maker_description", "model"),
            registration_date=_pick(payload, "registration_date", "regn_dt", "reg_date"),
            fitness_valid_upto=_pick(payload, "fitness_upto", "fitness_valid_upto", "fit_upto", "fitnessUpto"),
            source="vehicle API",
        )


def get_provider() -> VehicleProvider:
    if config.VEHICLE_PROVIDER == "mock":
        return MockVehicleProvider()
    if config.VEHICLE_PROVIDER == "http":
        return HttpVehicleProvider()
    raise ServiceUnavailable("VEHICLE_PROVIDER must be 'mock' or 'http'.")
