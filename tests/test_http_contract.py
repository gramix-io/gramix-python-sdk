"""Exercise every documented endpoint through the real HTTP transport."""

import json
import threading
import unittest
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from test_client import sample_order

from gramix import GramixClient


class HttpContractTests(unittest.TestCase):
    def test_all_endpoints_send_documented_requests_and_unwrap_responses(self) -> None:
        received: list[tuple[str, str, dict[str, str], bytes]] = []
        reply: dict[str, Any] = {}
        reply_status = 200

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                received.append(
                    (self.command, self.path, dict(self.headers.items()), body)
                )
                raw = json.dumps({"statusCode": reply_status, "data": reply}).encode()
                self.send_response(reply_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_POST = do_GET

            def log_message(self, format: str, *args: Any) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.shutdown)
        client = GramixClient(
            "contract-test-key",
            base_url=f"http://127.0.0.1:{server.server_port}/api/v1",
            timeout=5,
        )
        order = sample_order()
        purchase = {
            "orderId": order["id"],
            "status": "processing",
            "idempotencyKey": "contract_key_001",
        }
        cases: list[
            tuple[Callable[[], Any], str, str, dict[str, Any] | None, dict[str, Any]]
        ] = [
            (
                client.get_balance,
                "GET",
                "/wallets/balance",
                None,
                {"gram": "14.2500", "usdt": "125.5000"},
            ),
            (
                client.get_deposit_details,
                "POST",
                "/wallets/balance",
                None,
                {"address": "UQTEST", "memo": "test-memo"},
            ),
            (
                lambda: client.purchase_stars(
                    "telegram_user", "usdt", 500, "contract_key_001"
                ),
                "POST",
                "/purchase/stars",
                {
                    "recipientName": "telegram_user",
                    "paymentCurrency": "usdt",
                    "stars": 500,
                },
                purchase,
            ),
            (
                lambda: client.purchase_gram(
                    "telegram_user", "gram", 2, "contract_key_001"
                ),
                "POST",
                "/purchase/gram",
                {
                    "recipientName": "telegram_user",
                    "paymentCurrency": "gram",
                    "gram": 2,
                },
                purchase,
            ),
            (
                lambda: client.list_orders(limit=1, offset=10),
                "GET",
                "/orders?limit=1&offset=10",
                None,
                {"data": [order], "total": 42, "limit": 1, "offset": 10},
            ),
            (
                lambda: client.get_order(order["id"]),
                "GET",
                "/orders/f47ac10b-58cc-4372-a567-0e02b2c3d479",
                None,
                order,
            ),
        ]
        for duration in (3, 6, 12):

            def premium(months: Any = duration) -> Any:
                return client.purchase_premium(
                    "telegram_user", "gram", months, "contract_key_001"
                )

            cases.append(
                (
                    premium,
                    "POST",
                    f"/purchase/premium/{duration}",
                    {"recipientName": "telegram_user", "paymentCurrency": "gram"},
                    purchase,
                )
            )

        # Local traffic must not depend on a developer's HTTP proxy configuration.
        with patch("urllib.request.getproxies", return_value={}):
            for invoke, method, path, body, expected in cases:
                with self.subTest(method=method, path=path):
                    reply = expected
                    reply_status = 201 if method == "POST" else 200
                    received.clear()
                    self.assertEqual(invoke(), expected)
                    self.assertEqual(len(received), 1)
                    actual_method, actual_path, raw_headers, raw_body = received[0]
                    headers = {key.lower(): value for key, value in raw_headers.items()}
                    self.assertEqual(
                        (actual_method, actual_path), (method, "/api/v1" + path)
                    )
                    self.assertEqual(headers["x-api-key"], "contract-test-key")
                    self.assertEqual(headers["accept"], "application/json")
                    self.assertTrue(headers["user-agent"].startswith("gramix-python/"))
                    if body is None:
                        self.assertEqual(raw_body, b"")
                        self.assertNotIn("idempotency-key", headers)
                    else:
                        self.assertEqual(headers["content-type"], "application/json")
                        self.assertEqual(headers["idempotency-key"], "contract_key_001")
                        self.assertEqual(json.loads(raw_body), body)
