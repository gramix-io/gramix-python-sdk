from __future__ import annotations

import json
import math
import re
from typing import Any, Literal, cast
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request

from ._transport import Transport, http_transport
from ._validation import (
    MONEY_RE,
    ORDER_STATUSES,
    ORDER_TYPES,
    PROCESSING_STATUSES,
    UUID_RE,
    is_iso_timestamp,
)
from ._version import __version__
from .errors import ApiError, InvalidResponseError, TransportError
from .types import (
    DepositDetails,
    Order,
    OrderList,
    PaymentCurrency,
    PurchaseResponse,
    WalletBalance,
)

DEFAULT_BASE_URL = "https://api.gramix.io/api/v1"
USER_AGENT = f"gramix-python/{__version__}"
LiteralPremiumDuration = Literal[3, 6, 12]

_RECIPIENT_RE = re.compile(r"^[a-z][a-z0-9_]{4,31}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class GramixClient:
    """Synchronous, dependency-free client for Gramix API v1."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        if (
            not isinstance(api_key, str)
            or not api_key.strip()
            or "\r" in api_key
            or "\n" in api_key
        ):
            raise ValueError("API key must be a non-empty single-line string.")
        if not isinstance(base_url, str):
            raise ValueError("Base URL must be a string.")
        self._validate_base_url(base_url)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
            or (isinstance(timeout, float) and not math.isfinite(timeout))
        ):
            raise ValueError("Timeout must be greater than zero.")

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = http_transport if transport is None else transport

    def get_balance(self) -> WalletBalance:
        """Return GRAM and USDT balances as exact four-place decimal strings."""
        data, status = self._request("GET", "/wallets/balance")
        for field in ("gram", "usdt"):
            self._require_money(data, field, "wallet balance", status)
        return cast(WalletBalance, data)

    def get_deposit_details(self) -> DepositDetails:
        """Create or return the address and memo used to fund the wallet."""
        data, status = self._request("POST", "/wallets/balance")
        self._require_string(data, "address", "deposit details", status)
        self._require_string(data, "memo", "deposit details", status)
        return cast(DepositDetails, data)

    def purchase_stars(
        self,
        recipient_name: str,
        payment_currency: PaymentCurrency,
        stars: int,
        idempotency_key: str,
    ) -> PurchaseResponse:
        """Submit a Stars purchase; reuse the same key when retrying this purchase."""
        self._validate_purchase(recipient_name, payment_currency, idempotency_key)
        if (
            isinstance(stars, bool)
            or not isinstance(stars, int)
            or not 50 <= stars <= 1_000_000
        ):
            raise ValueError("Stars must be an integer between 50 and 1,000,000.")

        data, status = self._request(
            "POST",
            "/purchase/stars",
            body={
                "recipientName": recipient_name,
                "paymentCurrency": payment_currency,
                "stars": stars,
            },
            idempotency_key=idempotency_key,
        )
        return self._validate_purchase_response(data, status)

    def purchase_premium(
        self,
        recipient_name: str,
        payment_currency: PaymentCurrency,
        duration: LiteralPremiumDuration,
        idempotency_key: str,
    ) -> PurchaseResponse:
        """Submit a Premium purchase for 3, 6, or 12 months."""
        self._validate_purchase(recipient_name, payment_currency, idempotency_key)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration not in (3, 6, 12)
        ):
            raise ValueError("Premium duration must be 3, 6, or 12 months.")

        data, status = self._request(
            "POST",
            f"/purchase/premium/{duration}",
            body={
                "recipientName": recipient_name,
                "paymentCurrency": payment_currency,
            },
            idempotency_key=idempotency_key,
        )
        return self._validate_purchase_response(data, status)

    def purchase_gram(
        self,
        recipient_name: str,
        payment_currency: Literal["gram"],
        gram: int,
        idempotency_key: str,
    ) -> PurchaseResponse:
        """Submit an integer GRAM purchase paid from the GRAM balance."""
        self._validate_purchase(recipient_name, payment_currency, idempotency_key)
        if (
            isinstance(gram, bool)
            or not isinstance(gram, int)
            or not 1 <= gram <= 10_000
        ):
            raise ValueError("GRAM amount must be an integer between 1 and 10,000.")

        if payment_currency != "gram":
            raise ValueError('GRAM purchases require payment currency "gram".')

        data, status = self._request(
            "POST",
            "/purchase/gram",
            body={
                "recipientName": recipient_name,
                "paymentCurrency": payment_currency,
                "gram": gram,
            },
            idempotency_key=idempotency_key,
        )
        return self._validate_purchase_response(data, status)

    def list_orders(self, *, limit: int = 20, offset: int = 0) -> OrderList:
        """Return one page of API orders, newest first, with pagination metadata."""
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("Limit must be an integer between 1 and 100.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("Offset must be an integer greater than or equal to zero.")

        query = urlencode({"limit": limit, "offset": offset})
        data, status = self._request("GET", f"/orders?{query}")
        orders = data.get("data")
        if not isinstance(orders, list):
            raise self._invalid_data("order list", "data must be a list", status, data)
        for order in orders:
            if not isinstance(order, dict):
                raise self._invalid_data(
                    "order list", "every data item must be an object", status, data
                )
            self._validate_order(order, status)
        for field in ("total", "limit", "offset"):
            value = data.get(field)
            if isinstance(value, bool) or not isinstance(value, int):
                raise self._invalid_data(
                    "order list", f"{field} must be an integer", status, data
                )
            if value < (1 if field == "limit" else 0) or (
                field == "limit" and value > 100
            ):
                raise self._invalid_data(
                    "order list", f"{field} is outside its allowed range", status, data
                )
        return cast(OrderList, data)

    def get_order(self, order_id: str) -> Order:
        """Return an API order belonging to the authenticated account."""
        if not isinstance(order_id, str) or not UUID_RE.fullmatch(order_id):
            raise ValueError("Order ID must be a valid UUID.")
        data, status = self._request("GET", f"/orders/{quote(order_id, safe='')}")
        self._validate_order(data, status)
        return cast(Order, data)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        headers = {
            "Accept": "application/json",
            "x-api-key": self._api_key,
            "User-Agent": USER_AGENT,
        }
        encoded_body: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            encoded_body = json.dumps(
                body, separators=(",", ":"), allow_nan=False
            ).encode()
        if idempotency_key is not None:
            headers["idempotency-key"] = idempotency_key

        request = Request(
            self._base_url + path,
            data=encoded_body,
            headers=headers,
            method=method,
        )
        transport_result = self._transport(request, self._timeout)
        if (
            not isinstance(transport_result, tuple)
            or len(transport_result) != 2
            or isinstance(transport_result[0], bool)
            or not isinstance(transport_result[0], int)
            or not 100 <= transport_result[0] <= 599
            or not isinstance(transport_result[1], bytes)
        ):
            raise TransportError("Transport returned an invalid response.")
        status, raw_body = transport_result

        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            if 200 <= status < 300:
                raise InvalidResponseError(
                    "Gramix API returned invalid JSON.",
                    http_status=status,
                    raw_body=raw_body,
                ) from exc
            raise ApiError(
                f"Gramix API request failed with HTTP {status} and returned invalid JSON.",
                http_status=status,
                raw_body=raw_body,
            ) from exc

        if not isinstance(payload, dict) and not 200 <= status < 300:
            raise ApiError(
                f"Gramix API request failed with HTTP {status}.",
                http_status=status,
                raw_body=raw_body,
            )
        if not isinstance(payload, dict):
            raise InvalidResponseError(
                "Gramix API returned an invalid response.",
                http_status=status,
                raw_body=raw_body,
            )

        api_status = payload.get("statusCode")
        api_status_code = (
            api_status
            if isinstance(api_status, int) and not isinstance(api_status, bool)
            else None
        )
        if not 200 <= status < 300:
            message = payload.get("message")
            if not isinstance(message, str):
                message = f"Gramix API request failed with HTTP {status}."
            raise ApiError(
                message,
                http_status=status,
                api_status_code=api_status_code,
                response=payload,
                raw_body=raw_body,
            )

        if api_status_code is None:
            raise InvalidResponseError(
                "Gramix API response does not contain an integer statusCode.",
                http_status=status,
                response=payload,
                raw_body=raw_body,
            )
        if api_status_code != status:
            raise InvalidResponseError(
                "Gramix API statusCode does not match the HTTP status.",
                http_status=status,
                response=payload,
                raw_body=raw_body,
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise InvalidResponseError(
                "Gramix API response does not contain an object in data.",
                http_status=status,
                response=payload,
                raw_body=raw_body,
            )
        return data, status

    @staticmethod
    def _validate_purchase(
        recipient_name: str,
        payment_currency: str,
        idempotency_key: str,
    ) -> None:
        if not isinstance(recipient_name, str) or not _RECIPIENT_RE.fullmatch(
            recipient_name
        ):
            raise ValueError(
                "Recipient name must start with a lowercase Latin letter and "
                "contain 5–32 lowercase Latin letters, digits, or underscores, "
                "without @."
            )
        if payment_currency not in ("gram", "usdt"):
            raise ValueError('Payment currency must be "gram" or "usdt".')
        if not isinstance(idempotency_key, str) or not _IDEMPOTENCY_RE.fullmatch(
            idempotency_key
        ):
            raise ValueError(
                "Idempotency key must contain 8–64 Latin letters, digits, "
                "underscores, or hyphens."
            )

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        try:
            parts = urlsplit(base_url)
            hostname = parts.hostname
            parts.port
        except ValueError as exc:
            raise ValueError(
                "Base URL must be an absolute HTTP(S) URL without credentials, "
                "query, or fragment."
            ) from exc
        if (
            parts.scheme.lower() not in ("http", "https")
            or not hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError(
                "Base URL must be an absolute HTTP(S) URL without credentials, "
                "query, or fragment."
            )

    @classmethod
    def _validate_purchase_response(
        cls, data: dict[str, Any], status: int
    ) -> PurchaseResponse:
        cls._require_string(data, "orderId", "purchase response", status)
        cls._require_string(data, "status", "purchase response", status)
        cls._require_string(data, "idempotencyKey", "purchase response", status)
        if not UUID_RE.fullmatch(data["orderId"]):
            raise cls._invalid_data(
                "purchase response", "orderId must be a UUID", status, data
            )
        if data["status"] not in ORDER_STATUSES:
            raise cls._invalid_data(
                "purchase response", "status is not recognized", status, data
            )
        return cast(PurchaseResponse, data)

    @classmethod
    def _validate_order(cls, order: dict[str, Any], status: int) -> None:
        for field in (
            "id",
            "type",
            "method",
            "currency",
            "amount",
            "status",
            "processingStatus",
            "recipientName",
            "createdAt",
        ):
            cls._require_string(order, field, "order", status)
        if not UUID_RE.fullmatch(order["id"]):
            raise cls._invalid_data("order", "id must be a UUID", status, order)
        cls._require_money(order, "amount", "order", status)
        if not is_iso_timestamp(order["createdAt"]):
            raise cls._invalid_data(
                "order", "createdAt must be an ISO 8601 timestamp", status, order
            )
        if order["type"] not in ORDER_TYPES:
            raise cls._invalid_data("order", "type is not recognized", status, order)
        if order["method"] != "api":
            raise cls._invalid_data("order", "method must be api", status, order)
        if order["currency"] not in ("gram", "usd"):
            raise cls._invalid_data(
                "order", "currency is not recognized", status, order
            )
        if order["status"] not in ORDER_STATUSES:
            raise cls._invalid_data("order", "status is not recognized", status, order)
        if order["processingStatus"] not in PROCESSING_STATUSES:
            raise cls._invalid_data(
                "order", "processingStatus is not recognized", status, order
            )
        extra_data = order.get("extraData")
        if "extraData" not in order or (
            extra_data is not None and not isinstance(extra_data, dict)
        ):
            raise cls._invalid_data(
                "order", "extraData must be an object or null", status, order
            )
        if isinstance(extra_data, dict):
            for field in ("quantityStars", "quantityCoins"):
                if field in extra_data and (
                    isinstance(extra_data[field], bool)
                    or not isinstance(extra_data[field], int)
                ):
                    raise cls._invalid_data(
                        "order", f"extraData.{field} must be an integer", status, order
                    )
        for field in ("transactionHash", "idempotencyKey"):
            if field not in order or (
                order[field] is not None and not isinstance(order[field], str)
            ):
                raise cls._invalid_data(
                    "order", f"{field} must be a string or null", status, order
                )

    @classmethod
    def _require_money(
        cls, data: dict[str, Any], field: str, context: str, status: int
    ) -> None:
        cls._require_string(data, field, context, status)
        if not MONEY_RE.fullmatch(data[field]):
            raise cls._invalid_data(
                context,
                f"{field} must be a decimal string with four places",
                status,
                data,
            )

    @staticmethod
    def _require_string(
        data: dict[str, Any], field: str, context: str, status: int
    ) -> None:
        if not isinstance(data.get(field), str):
            raise GramixClient._invalid_data(
                context, f"{field} must be a string", status, data
            )

    @staticmethod
    def _invalid_data(
        context: str,
        reason: str,
        status: int,
        response: dict[str, Any],
    ) -> InvalidResponseError:
        return InvalidResponseError(
            f"Gramix API returned invalid {context} data: {reason}.",
            http_status=status,
            response=response,
        )
