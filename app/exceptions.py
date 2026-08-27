"""
Domain-level exceptions raised by services and translated into HTTP
responses by the API layer / exception handlers in main.py.
"""


class AppError(Exception):
    """Base class for all domain errors."""

    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class ValidationAppError(AppError):
    status_code = 422


class InactiveResourceError(AppError):
    status_code = 400


class UpstreamTimeoutError(AppError):
    status_code = 504

    def __init__(self, message: str):
        self.error_code = "n8n_timeout"
        self.http_status = None
        super().__init__(message)


class UpstreamError(AppError):
    status_code = 502

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "n8n_delivery_failed",
        http_status: int | None = None,
    ):
        self.error_code = error_code
        self.http_status = http_status
        super().__init__(message)


class UpstreamConnectionError(UpstreamError):
    status_code = 502

    def __init__(self, message: str):
        super().__init__(message, error_code="n8n_connection_failed")


class UpstreamConfigurationError(UpstreamError):
    status_code = 502

    def __init__(self, message: str):
        super().__init__(message, error_code="n8n_config_missing")
