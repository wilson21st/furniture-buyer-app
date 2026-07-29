"""Typed client for the external furniture-shop API (Steps 3–5).

Wraps every endpoint from the Participant Guide, sends ``X-Api-Key`` only where
required, maps each documented status code to a specific exception, and traces
each call as a Langfuse span (no-op unless observability is enabled).

Deliberate choices from the guide:
- Browsing uses ``/catalogue/search-index`` (no images). We never call plain
  ``/catalogue`` (it embeds every image as base64 and is very slow).
- ``get_product`` may return a base64 image field; we ignore it so images never
  leak into logs or an LLM's context.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app import observability
from app.config import get_settings


# --- Response models -------------------------------------------------------
class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_id: str
    product_name: str = ""
    price: float = 0.0
    category: str = ""
    colours: list[str] = []
    colour_count: int = 0
    link: str | None = None


class UserBalance(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    name: str = ""
    balance: float = 0.0


class OrderResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: str
    status: str = "success"
    total_price: float = 0.0
    remaining_balance: float = 0.0


class OrderRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: str
    item_id: str = ""
    quantity: int = 1
    total_price: float = 0.0
    status: str = "success"


# --- Exceptions ------------------------------------------------------------
class ApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class AuthError(ApiError):
    """401 — missing or invalid API key."""


class ForbiddenError(ApiError):
    """403 — key valid but for a different user."""


class NotFoundError(ApiError):
    """404 — unknown user or product."""


class InsufficientBalanceError(ApiError):
    """402 — order costs more than the remaining balance."""


class RateLimitError(ApiError):
    """429 — too many requests; retry after ``retry_after`` seconds."""

    def __init__(self, status_code: int, detail: str, retry_after: int = 0):
        self.retry_after = retry_after
        super().__init__(status_code, detail)


_STATUS_MAP = {
    401: AuthError,
    402: InsufficientBalanceError,
    403: ForbiddenError,
    404: NotFoundError,
}


# --- Client ----------------------------------------------------------------
class FurnitureAPI:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        user_id: str,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self._client = client or httpx.Client(timeout=15.0)

    @classmethod
    def from_settings(cls) -> FurnitureAPI:
        s = get_settings()
        return cls(s.furniture_api_base_url, s.furniture_api_key, s.furniture_user_id)

    def close(self) -> None:
        self._client.close()

    # -- core request with error mapping + tracing --
    def _request(
        self, method: str, path: str, *, auth: bool = False, **kwargs: Any
    ) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if auth:
            headers["X-Api-Key"] = self.api_key
        url = f"{self.base_url}{path}"
        with observability.span(f"furniture_api {method} {path}", method=method) as sp:
            response = self._client.request(method, url, headers=headers, **kwargs)
            sp.update(metadata={"status_code": response.status_code})
        self._raise_for_status(response)
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        status = response.status_code
        try:
            payload = response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
        except Exception:  # noqa: BLE001 - body may not be JSON
            detail = None
        detail = detail or response.text or f"HTTP {status}"
        if status == 429:
            retry_after = int(response.headers.get("Retry-After", 0) or 0)
            raise RateLimitError(status, detail, retry_after=retry_after)
        raise _STATUS_MAP.get(status, ApiError)(status, detail)

    # -- public catalogue (no auth) --
    def health(self) -> bool:
        try:
            return self._request("GET", "/health").is_success
        except ApiError:
            return False

    def list_categories(self) -> list[str]:
        return list(self._request("GET", "/catalogue/categories").json())

    def search_products(
        self, category: str | None = None, limit: int = 50, skip: int = 0
    ) -> list[Product]:
        params: dict[str, Any] = {"limit": limit, "skip": skip}
        if category:
            params["category"] = category
        data = self._request("GET", "/catalogue/search-index", params=params).json()
        return [Product.model_validate(item) for item in data]

    def get_product(self, item_id: str) -> Product:
        data = self._request("GET", f"/catalogue/{item_id}").json()
        return Product.model_validate(data)

    # -- account (auth) --
    def get_balance(self) -> UserBalance:
        data = self._request("GET", f"/users/{self.user_id}", auth=True).json()
        return UserBalance.model_validate(data)

    def place_order(self, item_id: str, quantity: int = 1) -> OrderResult:
        body = {"user_id": self.user_id, "item_id": item_id, "quantity": quantity}
        data = self._request("POST", "/orders", auth=True, json=body).json()
        return OrderResult.model_validate(data)

    def order_history(self) -> list[OrderRecord]:
        data = self._request("GET", f"/orders/{self.user_id}", auth=True).json()
        return [OrderRecord.model_validate(item) for item in data]
