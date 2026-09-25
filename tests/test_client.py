import json
import unittest
from typing import Any, cast
from urllib.request import Request

from gramix import (
    ApiError,
    GramixClient,
    InvalidResponseError,
    parse_webhook_event,
)


def sample_order() -> dict[str, Any]:
    return {
        "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "type": "stars",
        "method": "api",
        "currency": "usd",
        "amount": "1.5500",
        "status": "completed",
        "processingStatus": "completed_fragment_purchase",
        "recipientName": "telegram_user",
        "extraData": {"quantityCoins": 100},
        "transactionHash": None,
        "idempotencyKey": "stars_test_0001",
        "createdAt": "2026-07-16T12:00:00.000Z",
    }


class ClientTests(unittest.TestCase):
    def test_purchase_stars_builds_documented_request(self) -> None:
        calls: list[tuple[Request, float]] = []

        def transport(request: Request, timeout: float) -> tuple[int, bytes]:
            calls.append((request, timeout))
            return 201, json.dumps(
                {
                    "statusCode": 201,
                    "data": {
                        "orderId": "7ba77616-7706-4215-9e6f-b6c67e4df292",
                        "status": "processing",
                        "idempotencyKey": "stars_test_0001",
                    },
                }
            ).encode()

        client = GramixClient(
            "test-key",
            base_url="https://example.test/api/v1",
            timeout=5,
            transport=transport,
        )
        result = client.purchase_stars("telegram_user", "usdt", 500, "stars_test_0001")

        request, timeout = calls[0]
        self.assertEqual(result["status"], "processing")
        self.assertEqual(request.full_url, "https://example.test/api/v1/purchase/stars")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Idempotency-key"), "stars_test_0001")
        self.assertIsInstance(request.data, bytes)
        request_data = cast(bytes, request.data)
        self.assertEqual(json.loads(request_data)["stars"], 500)
        self.assertEqual(timeout, 5)

    def test_gram_rejects_invalid_amounts_before_transport(self) -> None:
        def transport(request: Request, timeout: float) -> tuple[int, bytes]:
            self.fail("Invalid purchase must not reach the API")

        client = GramixClient("test-key", transport=transport)
        for amount in (0, 10001, True, 2.5, 2.0, float("nan"), float("inf"), "2"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                client.purchase_gram(
                    "telegram_user", "gram", cast(Any, amount), "gram_test_0001"
                )

    def test_gram_rejects_usdt_before_transport(self) -> None:
        def transport(request: Request, timeout: float) -> tuple[int, bytes]:
            self.fail("Invalid currency must not reach the API")

        with self.assertRaises(ValueError):
            GramixClient("test-key", transport=transport).purchase_gram(
                "telegram_user", cast(Any, "usdt"), 2, "gram_test_0001"
            )

    def test_premium_rejects_float_duration_before_transport(self) -> None:
        def transport(request: Request, timeout: float) -> tuple[int, bytes]:
            self.fail("Invalid duration must not reach the API")

        with self.assertRaises(ValueError):
            GramixClient("test-key", transport=transport).purchase_premium(
                "telegram_user", "gram", cast(Any, 6.0), "premium_test_0001"
            )

    def test_api_error_preserves_diagnostics(self) -> None:
        raw_body = b'{"statusCode":403,"message":"Insufficient balance"}'

        def transport(_: Request, __: float) -> tuple[int, bytes]:
            return 403, raw_body

        client = GramixClient("test-key", transport=transport)
        with self.assertRaises(ApiError) as caught:
            client.get_balance()

        self.assertEqual(caught.exception.http_status, 403)
        self.assertEqual(caught.exception.api_status_code, 403)
        self.assertEqual(caught.exception.raw_body, raw_body)
        self.assertEqual(str(caught.exception), "Insufficient balance")

    def test_all_documented_endpoint_routes(self) -> None:
        routes: list[tuple[str, str]] = []

        def transport(request: Request, _: float) -> tuple[int, bytes]:
            self.assertIsNotNone(request.method)
            routes.append((cast(str, request.method), request.full_url))
            status = 201 if request.method == "POST" else 200
            data: dict[str, Any]
            if request.full_url.endswith("/wallets/balance"):
                data = (
                    {"gram": "14.2500", "usdt": "125.5000"}
                    if request.method == "GET"
                    else {"address": "UQTEST", "memo": "test-memo"}
                )
            elif "/purchase/" in request.full_url:
                data = {
                    "orderId": "7ba77616-7706-4215-9e6f-b6c67e4df292",
                    "status": "processing",
                    "idempotencyKey": "route_test_0001",
                }
            elif "/orders?" in request.full_url:
                data = {
                    "data": [sample_order()],
                    "total": 1,
                    "limit": 100,
                    "offset": 10,
                }
            else:
                data = sample_order()
            return status, json.dumps({"statusCode": status, "data": data}).encode()

        client = GramixClient(
            "test-key",
            base_url="https://example.test/api/v1",
            transport=transport,
        )
        client.get_balance()
        client.get_deposit_details()
        client.purchase_stars("telegram_user", "usdt", 50, "stars_route_0001")
        client.purchase_premium("telegram_user", "gram", 6, "premium_route_0001")
        client.purchase_gram("telegram_user", "gram", 1, "gram_route_0001")
        client.list_orders(limit=100, offset=10)
        client.get_order("f47ac10b-58cc-4372-a567-0e02b2c3d479")

        self.assertEqual(
            routes,
            [
                ("GET", "https://example.test/api/v1/wallets/balance"),
                ("POST", "https://example.test/api/v1/wallets/balance"),
                ("POST", "https://example.test/api/v1/purchase/stars"),
                ("POST", "https://example.test/api/v1/purchase/premium/6"),
                ("POST", "https://example.test/api/v1/purchase/gram"),
                ("GET", "https://example.test/api/v1/orders?limit=100&offset=10"),
                (
                    "GET",
                    "https://example.test/api/v1/orders/"
                    "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                ),
            ],
        )

    def test_invalid_success_response_is_rejected(self) -> None:
        client = GramixClient(
            "test-key",
            transport=lambda _request, _timeout: (
                200,
                b'{"statusCode":200,"data":{"gram":12,"usdt":"1.0000"}}',
            ),
        )
        with self.assertRaises(InvalidResponseError) as caught:
            client.get_balance()
        self.assertEqual(caught.exception.http_status, 200)

    def test_order_extra_data_matches_declared_types(self) -> None:
        for field in ("quantityStars", "quantityCoins"):
            for value in ("100", True, 1.5, None):
                with self.subTest(field=field, value=value):
                    order = {**sample_order(), "extraData": {field: value}}
                    client = GramixClient(
                        "test-key",
                        transport=lambda r, t: (
                            200,
                            json.dumps({"statusCode": 200, "data": order}).encode(),
                        ),
                    )
                    with self.assertRaises(InvalidResponseError):
                        client.get_order(order["id"])

    def test_order_extra_data_accepts_optional_and_unknown_fields(self) -> None:
        for extra in (
            None,
            {},
            {"quantityCoins": 100},
            {"quantityStars": 50},
            {"future": "value"},
        ):
            with self.subTest(extra=extra):
                order = {**sample_order(), "extraData": extra}
                client = GramixClient(
                    "test-key",
                    transport=lambda r, t: (
                        200,
                        json.dumps({"statusCode": 200, "data": order}).encode(),
                    ),
                )
                self.assertEqual(client.get_order(order["id"])["extraData"], extra)

    def test_local_validation(self) -> None:
        client = GramixClient(
            "test-key",
            transport=lambda _request, _timeout: (
                200,
                b'{"statusCode":200,"data":{}}',
            ),
        )
        with self.assertRaises(ValueError):
            client.purchase_premium(
                "telegram_user",
                "usdt",
                cast(Any, 4),
                "premium_test_0001",
            )
        with self.assertRaises(ValueError):
            client.purchase_stars("1username", "usdt", 50, "stars_test_0001")
        with self.assertRaises(ValueError):
            client.list_orders(limit=101)
        with self.assertRaises(ValueError):
            client.get_order("not-a-uuid")
        with self.assertRaises(ValueError):
            GramixClient("test-key", base_url="file:///tmp/api")

    def test_webhook_parser_validates_event_coherence(self) -> None:
        event = parse_webhook_event(
            {
                "event": "order.completed",
                "orderId": "7ba77616-7706-4215-9e6f-b6c67e4df292",
                "status": "completed",
                "processingStatus": "completed_fragment_purchase",
                "type": "stars",
                "amount": "7.6500",
                "currency": "usd",
                "recipientName": "telegram_user",
                "createdAt": "2026-07-13T10:20:30.000Z",
            }
        )
        self.assertEqual(event["status"], "completed")
        with self.assertRaises(ValueError):
            parse_webhook_event({**event, "status": "failed"})


if __name__ == "__main__":
    unittest.main()
