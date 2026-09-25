"""Malformed data must not cross the SDK's typed response boundary."""

import json
import unittest
from typing import Any

from test_client import sample_order

from gramix import GramixClient, InvalidResponseError, parse_webhook_event


def client_with(data: dict[str, Any], status_code: int = 200) -> GramixClient:
    return GramixClient(
        "test-key",
        transport=lambda r, t: (
            200,
            json.dumps({"statusCode": status_code, "data": data}).encode(),
        ),
    )


def sample_event() -> dict[str, Any]:
    order = sample_order()
    return {
        key: value
        for key, value in {
            **order,
            "event": "order.completed",
            "orderId": order["id"],
        }.items()
        if key not in ("id", "method", "extraData", "transactionHash", "idempotencyKey")
    }


class ResponseContractTests(unittest.TestCase):
    def test_money_rejects_non_decimal_strings(self) -> None:
        for amount in (
            "",
            "NaN",
            "Infinity",
            "1e4",
            "1.5",
            "1.00000",
            " 1.0000",
            "١.0000",
        ):
            with self.subTest(amount=amount):
                for field in ("gram", "usdt"):
                    balance = {"gram": "0.0000", "usdt": "0.0000", field: amount}
                    with self.assertRaises(InvalidResponseError):
                        client_with(balance).get_balance()
                order = {**sample_order(), "amount": amount}
                with self.assertRaises(InvalidResponseError):
                    client_with(order).get_order(order["id"])
                with self.assertRaises(ValueError):
                    parse_webhook_event({**sample_event(), "amount": amount})

    def test_money_preserves_precision_and_unknown_fields(self) -> None:
        for amount in ("0.0000", "12345678901234567890.1234", "-1.0000"):
            balance = {"gram": amount, "usdt": "0.0000", "future": {"key": 1}}
            self.assertEqual(client_with(balance).get_balance(), balance)

    def test_invalid_timestamps_are_rejected(self) -> None:
        for timestamp in (
            "",
            "yesterday",
            "2026-02-30T12:00:00Z",
            "2026-07-16",
            "2026-07-16T25:00:00Z",
        ):
            with self.subTest(timestamp=timestamp):
                order = {**sample_order(), "createdAt": timestamp}
                with self.assertRaises(InvalidResponseError):
                    client_with(order).get_order(order["id"])
                with self.assertRaises(ValueError):
                    parse_webhook_event({**sample_event(), "createdAt": timestamp})

    def test_iso_timestamps_are_preserved(self) -> None:
        for timestamp in (
            "2026-07-16T12:00:00.000Z",
            "2026-07-16T14:00:00+02:00",
            "2026-07-16T12:00:00",
        ):
            order = {**sample_order(), "createdAt": timestamp}
            self.assertEqual(
                client_with(order).get_order(order["id"])["createdAt"], timestamp
            )
            self.assertEqual(
                parse_webhook_event({**sample_event(), "createdAt": timestamp})[
                    "createdAt"
                ],
                timestamp,
            )

    def test_response_pagination_bounds(self) -> None:
        for field, value in (
            ("total", -1),
            ("offset", -1),
            ("limit", 0),
            ("limit", 101),
            ("total", True),
        ):
            with self.subTest(field=field, value=value):
                page = {"data": [], "total": 0, "limit": 20, "offset": 0, field: value}
                with self.assertRaises(InvalidResponseError):
                    client_with(page).list_orders()
        # An offset beyond total is legal and returns an empty page.
        page = {"data": [], "total": 0, "limit": 100, "offset": 50}
        self.assertEqual(client_with(page).list_orders(offset=50), page)

    def test_inconsistent_status_envelope_is_rejected(self) -> None:
        for status in (201, 400, 500):
            with self.subTest(status=status), self.assertRaises(InvalidResponseError):
                client_with({"gram": "0.0000", "usdt": "0.0000"}, status).get_balance()

    def test_uuid_versions_are_not_limited_to_legacy_versions(self) -> None:
        for order_id in (
            "0190bdbc-7706-7215-9e6f-b6c67e4df292",
            "0190bdbc-7706-8215-9e6f-b6c67e4df292",
        ):
            with self.subTest(order_id=order_id):
                order = {**sample_order(), "id": order_id}
                self.assertEqual(client_with(order).get_order(order_id)["id"], order_id)
                self.assertEqual(
                    parse_webhook_event({**sample_event(), "orderId": order_id})[
                        "orderId"
                    ],
                    order_id,
                )
