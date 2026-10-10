"""Small exception classes. main.py turns them into HTTP responses."""


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequest(AppError):
    status_code = 400


class NotFoundError(AppError):
    status_code = 404


class DuplicateError(AppError):
    status_code = 409


class ValidationFailed(AppError):
    status_code = 422


class ServiceUnavailable(AppError):
    status_code = 503


class UpstreamError(AppError):
    """An external service (e.g. the vehicle-data API) failed or answered badly."""

    status_code = 502
