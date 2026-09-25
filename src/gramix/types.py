from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

PaymentCurrency = Literal["gram", "usdt"]
OrderStatus = Literal["created", "processing", "completed", "failed", "canceled"]
OrderType = Literal[
    "stars",
    "gram_coins",
    "premium_3_month",
    "premium_6_month",
    "premium_12_month",
]
ProcessingStatus = Literal[
    "pending_processing",
    "payment_verified",
    "completed_fragment_purchase",
    "failure_verify_payment",
    "failure_fragment_purchase",
    "retrying_fragment_purchase",
]


class WalletBalance(TypedDict):
    gram: str
    usdt: str


class DepositDetails(TypedDict):
    address: str
    memo: str


class PurchaseResponse(TypedDict):
    orderId: str
    status: OrderStatus
    idempotencyKey: str


class ExtraData(TypedDict):
    quantityStars: NotRequired[int]
    quantityCoins: NotRequired[int]


class Order(TypedDict):
    id: str
    type: OrderType
    method: Literal["api"]
    currency: Literal["gram", "usd"]
    amount: str
    status: OrderStatus
    processingStatus: ProcessingStatus
    recipientName: str
    extraData: ExtraData | None
    transactionHash: str | None
    idempotencyKey: str | None
    createdAt: str


class OrderList(TypedDict):
    data: list[Order]
    total: int
    limit: int
    offset: int


class WebhookEvent(TypedDict):
    event: Literal["order.completed", "order.failed"]
    orderId: str
    status: Literal["completed", "failed"]
    processingStatus: ProcessingStatus
    type: str
    amount: str
    currency: Literal["gram", "usd"]
    recipientName: str
    createdAt: str
