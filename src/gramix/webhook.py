from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ._validation import MONEY_RE, PROCESSING_STATUSES, UUID_RE, is_iso_timestamp
from .types import WebhookEvent


def parse_webhook_event(payload: Mapping[str, Any]) -> WebhookEvent:
    """Validate and type an order webhook payload.

    This validates the documented payload shape only. It does not authenticate
    the sender because the public API documentation does not define a signature.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("Webhook payload must be an object.")

    fields = (
        "event",
        "orderId",
        "status",
        "processingStatus",
        "type",
        "amount",
        "currency",
        "recipientName",
        "createdAt",
    )
    for field in fields:
        if not isinstance(payload.get(field), str):
            raise ValueError(f"Webhook field {field} must be a string.")

    event = payload["event"]
    if event not in ("order.completed", "order.failed"):
        raise ValueError("Webhook event is not recognized.")
    expected_status = "completed" if event == "order.completed" else "failed"
    if payload["status"] != expected_status:
        raise ValueError("Webhook event and status do not match.")
    if not UUID_RE.fullmatch(payload["orderId"]):
        raise ValueError("Webhook orderId must be a valid UUID.")
    event_type = payload["type"]
    if event_type not in ("stars", "gram") and not event_type.startswith("premium_"):
        raise ValueError("Webhook type is not recognized.")
    if payload["currency"] not in ("gram", "usd"):
        raise ValueError("Webhook currency is not recognized.")
    if payload["processingStatus"] not in PROCESSING_STATUSES:
        raise ValueError("Webhook processingStatus is not recognized.")
    if not MONEY_RE.fullmatch(payload["amount"]):
        raise ValueError("Webhook amount must be a decimal string with four places.")
    if not is_iso_timestamp(payload["createdAt"]):
        raise ValueError("Webhook createdAt must be an ISO 8601 timestamp.")

    return cast(WebhookEvent, dict(payload))
