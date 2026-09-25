import io
import unittest
from email.message import Message
from http.client import IncompleteRead
from typing import Any
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import Request
from urllib.response import addinfourl

from gramix import ApiError, GramixClient, TransportError


def response(body: bytes, status: int, *, location: str | None = None) -> Any:
    headers = Message()
    if location:
        headers["Location"] = location
    result: Any = addinfourl(
        io.BytesIO(body), headers, "http://api.example/balance", status
    )
    result.msg = "Test response"
    return result


class TransportTests(unittest.TestCase):
    def test_redirects_are_not_followed(self) -> None:
        for code in (301, 302, 303, 307, 308):
            for target in (
                "http://other.example/balance",
                "http://api.example/elsewhere",
            ):
                with self.subTest(code=code, target=target):
                    calls: list[Request] = []

                    def http_open(request: Request) -> Any:
                        calls.append(request)
                        if len(calls) == 1:
                            return response(b"redirect", code, location=target)
                        return response(
                            b'{"statusCode":200,"data":{"gram":"1.0000","usdt":"0.0000"}}',
                            200,
                        )

                    with patch(
                        "urllib.request.HTTPHandler.http_open", side_effect=http_open
                    ):
                        with self.assertRaises(ApiError) as caught:
                            GramixClient(
                                "test-key", base_url="http://api.example"
                            ).get_balance()
                    self.assertEqual(caught.exception.http_status, code)
                    self.assertEqual(len(calls), 1)

    def test_purchase_redirect_does_not_send_a_second_request(self) -> None:
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                calls: list[Request] = []

                def http_open(request: Request) -> Any:
                    calls.append(request)
                    return response(
                        b"redirect", code, location="http://other.example/purchase"
                    )

                with patch(
                    "urllib.request.HTTPHandler.http_open", side_effect=http_open
                ):
                    with self.assertRaises(ApiError) as caught:
                        GramixClient(
                            "test-key", base_url="http://api.example"
                        ).purchase_stars(
                            "telegram_user", "gram", 50, "purchase_test_0001"
                        )
                self.assertEqual(caught.exception.http_status, code)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].get_method(), "POST")

    def test_connection_errors_are_wrapped(self) -> None:
        for error in (
            URLError("offline"),
            TimeoutError("timeout"),
            IncompleteRead(b"partial", 100),
        ):
            with self.subTest(error=error):
                with patch("urllib.request.HTTPHandler.http_open", side_effect=error):
                    with self.assertRaises(TransportError) as caught:
                        GramixClient(
                            "test-key", base_url="http://api.example"
                        ).get_balance()
                self.assertIs(caught.exception.__cause__, error)

    def test_incomplete_body_is_wrapped_and_closed(self) -> None:
        for code in (200, 403):
            with self.subTest(code=code):
                reply = response(b"", code)
                error = IncompleteRead(b"partial", 100)
                with patch.object(reply, "read", side_effect=error):
                    with patch(
                        "urllib.request.HTTPHandler.http_open", return_value=reply
                    ):
                        with self.assertRaises(TransportError) as caught:
                            GramixClient(
                                "test-key", base_url="http://api.example"
                            ).get_balance()
                self.assertIs(caught.exception.__cause__, error)
                self.assertTrue(reply.closed)

    def test_http_error_body_is_preserved_and_closed(self) -> None:
        raw = b'{"statusCode":403,"message":"Insufficient balance"}'
        reply = response(raw, 403)
        with patch("urllib.request.HTTPHandler.http_open", return_value=reply):
            with self.assertRaises(ApiError) as caught:
                GramixClient("test-key", base_url="http://api.example").get_balance()
        self.assertEqual(caught.exception.raw_body, raw)
        self.assertEqual(caught.exception.http_status, 403)
        self.assertTrue(reply.closed)

    def test_successful_http_response_is_closed(self) -> None:
        reply = response(
            b'{"statusCode":200,"data":{"gram":"1.0000","usdt":"0.0000"}}', 200
        )
        with patch("urllib.request.HTTPHandler.http_open", return_value=reply):
            result = GramixClient(
                "test-key", base_url="http://api.example"
            ).get_balance()
        self.assertEqual(result["gram"], "1.0000")
        self.assertTrue(reply.closed)
