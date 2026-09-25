"""Shared API schema rules; enum values come from the public type definitions."""

import re
from datetime import datetime
from typing import get_args

from .types import OrderStatus, OrderType, ProcessingStatus

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
ORDER_STATUSES = frozenset(get_args(OrderStatus))
ORDER_TYPES = frozenset(get_args(OrderType))
PROCESSING_STATUSES = frozenset(get_args(ProcessingStatus))
MONEY_RE = re.compile(r"-?[0-9]+\.[0-9]{4}")


def is_iso_timestamp(value: str) -> bool:
    """Accept ISO 8601 datetimes, including UTC and offset representations."""
    if "T" not in value:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True
