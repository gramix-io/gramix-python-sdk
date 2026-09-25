"""Standard-library HTTP transport with explicit redirect and error handling."""

from collections.abc import Callable
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .errors import TransportError

Transport = Callable[[Request, float], tuple[int, bytes]]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        # Let urllib report the original 3xx as HTTPError without another request.
        return None


def http_transport(request: Request, timeout: float) -> tuple[int, bytes]:
    try:
        try:
            with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
                return response.status, response.read()
        except HTTPError as exc:
            with exc:
                return exc.code, exc.read()
    except (URLError, OSError, HTTPException) as exc:
        raise TransportError(f"Gramix API request failed: {exc}") from exc
