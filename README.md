# Gramix API client for Python (Unofficial Fragment API)

A synchronous, fully typed client requiring Python 3.11+. It uses the standard
library and has no runtime dependencies.

## Installation

From a clone of the standalone GitHub repository:

```bash
python -m pip install .
```

Once the `v1.0.0` tag is published, install that release directly (requires Git):

```bash
python -m pip install "gramix-api @ git+https://github.com/gramix-io/gramix-python-sdk.git@v1.0.0"
```

Alternatively, install the wheel attached to a GitHub Release with
`python -m pip install ./gramix_api-1.0.0-py3-none-any.whl`.
PyPI installation is available only after a separate PyPI publication.

## Quick start

Set `GRAMIX_API_KEY` in your environment. Purchase examples below create real,
paid orders when executed with an active key. Persist each idempotency key
before sending its request; generate a distinct key (for example `uuid.uuid4().hex`)
for every new purchase.

```python
import os
from gramix import GramixClient

client = GramixClient(os.environ["GRAMIX_API_KEY"])

balance = client.get_balance()
deposit = client.get_deposit_details()

purchase = client.purchase_stars(
    recipient_name="telegram_user",
    payment_currency="usdt",
    stars=500,
    idempotency_key="stars_20260729_0001",
)

premium = client.purchase_premium(
    recipient_name="telegram_user",
    payment_currency="gram",
    duration=6,
    idempotency_key="premium_20260729_0001",
)

gram = client.purchase_gram(
    recipient_name="telegram_user",
    payment_currency="gram",
    gram=2,
    idempotency_key="gram_20260729_0001",
)

orders = client.list_orders(limit=20, offset=0)
order = client.get_order(purchase["orderId"])
```

Every method returns the contents of the successful response's `data` field.
The client validates the documented structure before returning it.

## API methods

All paths below are relative to `https://api.gramix.io/api/v1`.

| Python method | HTTP endpoint | Arguments / result |
| --- | --- | --- |
| `get_balance()` | `GET /wallets/balance` | Decimal strings: `gram`, `usdt` |
| `get_deposit_details()` | `POST /wallets/balance` | TON `address` and required `memo` |
| `purchase_stars(recipient_name, payment_currency, stars, idempotency_key)` | `POST /purchase/stars` | 50–1,000,000 integer Stars; `gram` or `usdt` |
| `purchase_premium(recipient_name, payment_currency, duration, idempotency_key)` | `POST /purchase/premium/{duration}` | 3, 6, or 12 integer months; `gram` or `usdt` |
| `purchase_gram(recipient_name, payment_currency, gram, idempotency_key)` | `POST /purchase/gram` | 1–10,000 integer GRAM; payment currency `gram` |
| `list_orders(limit=20, offset=0)` | `GET /orders` | `data`, `total`, `limit`, `offset`; limit 1–100 |
| `get_order(order_id)` | `GET /orders/{id}` | One order by UUID |

Python arguments use `snake_case`; the client sends the API's `camelCase` JSON
fields. Returned values are typed dictionaries retaining the original API keys.
GET requests and deposit requests have no JSON body. Purchase requests carry
`Content-Type: application/json` and `idempotency-key`; every request includes
`x-api-key` and `Accept: application/json`.

Recipients use lowercase Telegram usernames without `@`. Idempotency keys
contain 8–64 ASCII letters, digits, underscores, or hyphens.
Always include the deposit memo in the TON transfer. A purchase response means
acceptance for asynchronous processing; use `get_order(purchase["orderId"])`
or webhooks to track completion. Order currency uses `usd` for USDT payments.
Keep monetary values as strings or use `decimal.Decimal`, avoiding float rounding.

```python
from decimal import Decimal

available_usdt = Decimal(balance["usdt"])
```

Balances and amounts must be decimal strings with four fractional digits.
Order and webhook timestamps are validated as ISO 8601 datetimes and retained
as strings. Unknown response fields are retained for forward compatibility.

## Pagination

```python
offset = 0
while True:
    page = client.list_orders(limit=100, offset=offset)
    for order in page["data"]:
        print(order["id"], order["status"])
    offset += len(page["data"])
    if not page["data"] or offset >= page["total"]:
        break
```

Orders are newest first. New orders arriving during pagination can shift offsets;
deduplicate by `id` when collecting a changing order history.

The contract is documented in the [Gramix API reference](https://gramix.io/resellers/api/documentation).

## Errors

- Non-2xx responses raise `ApiError` and preserve `http_status`,
  `api_status_code`, `response`, and `raw_body`.
- Network, timeout, and incomplete HTTP response failures raise `TransportError`.
- Redirects are not followed; HTTP 3xx responses raise `ApiError` without
  sending the API key or purchase request to the redirect destination.
- Successful but malformed responses raise `InvalidResponseError`.
- Invalid method arguments raise `ValueError`.

All SDK response and transport exceptions inherit from `GramixError`:

```python
from gramix import ApiError, InvalidResponseError, TransportError

try:
    balance = client.get_balance()
except ApiError as exc:
    print(f"API rejected the request: HTTP {exc.http_status}")
except TransportError:
    print("Request outcome is unknown; check connectivity before retrying.")
except InvalidResponseError:
    print("The API response does not match the documented format.")
```

Do not automatically repeat a purchase with a new idempotency key after a
network error. Retry the same request with the same key; use a new key only for
a new purchase. The SDK does not retry automatically. The same precaution applies
when a purchase returns an unreadable or malformed response.

## Webhooks

```python
import json
from gramix import parse_webhook_event

event = parse_webhook_event(json.loads(request_body))
```

This validates the documented payload shape but does not authenticate the
sender. The public API documentation currently defines no webhook signature.
Confirm order state with `get_order(event["orderId"])` before granting value.
Return HTTP 2xx promptly, handle duplicates idempotently, and do not assume
events arrive in order.

The constructor accepts `base_url`, `timeout`, and a custom `transport` for
private gateways and tests. A custom base URL receives the API key, so use only
a trusted HTTP(S) endpoint. Custom transports implement
`Callable[[Request, float], tuple[int, bytes]]` and are responsible for redirect
policy, response cleanup, and wrapping network errors in `TransportError`.

## Development

```bash
python -m pip install -e ".[dev]"
PYTHONPATH=src python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m mypy src/gramix tests
python -m build
python -m twine check dist/*
```

Tests use fixtures and a local HTTP server; they require no API key and create
no real purchases. CI tests Python 3.11–3.14 on Linux and 3.11/3.14 on Windows
and macOS, and checks typing, lint, formatting, and distributable artifacts.

## Releases

Update `src/gramix/_version.py` and `CHANGELOG.md`, then push the commit to
`main`. Once CI passes, create and push a matching version tag (for example,
`v1.0.0`):

```bash
git tag v1.0.0
git push origin v1.0.0
```

The tag workflow checks the package version and runs the full CI matrix. If all
jobs pass, it publishes a GitHub Release with the wheel and source distribution
attached. A failed job does not publish a release. This does not upload to PyPI.

## License

[MIT](./LICENSE), copyright Gramix.io. Commercial use, modification, and
redistribution are allowed under the license terms.
