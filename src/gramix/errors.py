from __future__ import annotations

from typing import Any


class GramixError(Exception):
    """Base class for Gramix client errors."""


class TransportError(GramixError):
    """Raised when the API cannot be reached."""


class InvalidResponseError(GramixError):
    """Raised when a successful API response violates the documented schema."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int,
        response: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.response = response
        self.raw_body = raw_body


class ApiError(GramixError):
    """Raised for a non-2xx HTTP response, including malformed error bodies."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int,
        api_status_code: int | None = None,
        response: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.api_status_code = api_status_code
        self.response = response
        self.raw_body = raw_body
