"""
zoho.py — Zoho Books API client.

Handles:
  - OAuth2 access-token refresh (using refresh_token grant)
  - Fetching all items from Zoho Books → stored in product_cache
  - Creating a purchase bill after user confirmation
"""

import os
import logging
from datetime import datetime, timezone
import httpx
from backend.db import product_cache

logger = logging.getLogger(__name__)

# ── Config (from environment) ────────────────────────────────────────────────

ZOHO_TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"
ZOHO_API_BASE = "https://www.zohoapis.in/books/v3"

_access_token: str | None = None


def _get_config() -> dict:
    return {
        "client_id": os.environ["ZOHO_CLIENT_ID"],
        "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
        "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"],
        "organization_id": os.environ["ZOHO_ORGANIZATION_ID"],
    }


# ── Token management ─────────────────────────────────────────────────────────

def refresh_access_token() -> str:
    """
    Exchange the refresh token for a new access token.
    Zoho access tokens expire after 1 hour.
    """
    global _access_token
    cfg = _get_config()
    response = httpx.post(
        ZOHO_TOKEN_URL,
        params={
            "grant_type": "refresh_token",
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": cfg["refresh_token"],
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if "access_token" not in data:
        raise RuntimeError(f"Zoho token refresh failed: {data}")
    _access_token = data["access_token"]
    logger.info("Zoho access token refreshed successfully")
    return _access_token


def _token() -> str:
    global _access_token
    if not _access_token:
        refresh_access_token()
    return _access_token


def _headers() -> dict:
    return {"Authorization": f"Zoho-oauthtoken {_token()}"}


def _org_params() -> dict:
    return {"organization_id": _get_config()["organization_id"]}


# ── Item sync ────────────────────────────────────────────────────────────────

def fetch_items() -> int:
    """
    Fetch all active items from Zoho Books and replace the local product_cache.
    Returns the count of items synced.
    """
    all_items = []
    page = 1

    while True:
        resp = httpx.get(
            f"{ZOHO_API_BASE}/items",
            headers=_headers(),
            params={**_org_params(), "page": page, "per_page": 200},
            timeout=30,
        )
        if resp.status_code == 401:
            # Token expired — refresh and retry once
            refresh_access_token()
            resp = httpx.get(
                f"{ZOHO_API_BASE}/items",
                headers=_headers(),
                params={**_org_params(), "page": page, "per_page": 200},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        all_items.extend(items)

        page_context = data.get("page_context", {})
        if not page_context.get("has_more_page", False):
            break
        page += 1

    # Replace cache
    col = product_cache()
    col.delete_many({})
    if all_items:
        now = datetime.now(timezone.utc)
        col.insert_many(
            [
                {
                    "zoho_item_id": str(item["item_id"]),
                    "name": item["name"],
                    "rate": item.get("rate", 0.0),
                    "mrp": item.get("custom_fields_hash", {}).get("cf_mrp", None),
                    "last_synced_at": now,
                }
                for item in all_items
            ]
        )

    logger.info("Zoho sync complete — %d items cached", len(all_items))
    return len(all_items)


# ── Bill creation ────────────────────────────────────────────────────────────

def create_bill(
    vendor_id: str,
    invoice_number: str,
    invoice_date: str,
    line_items: list[dict],
) -> dict:
    """
    Create a purchase bill in Zoho Books.

    line_items: list of {
        item_id: str,
        quantity: float,
        rate: float,
        name: str,
    }

    Returns the Zoho API response body.
    """
    payload = {
        "vendor_id": vendor_id,
        "bill_number": invoice_number,
        "date": invoice_date,
        "line_items": [
            {
                "item_id": li["item_id"],
                "name": li["name"],
                "quantity": li["quantity"],
                "rate": li["rate"],
            }
            for li in line_items
        ],
    }

    resp = httpx.post(
        f"{ZOHO_API_BASE}/bills",
        headers=_headers(),
        params=_org_params(),
        json=payload,
        timeout=30,
    )
    if resp.status_code == 401:
        refresh_access_token()
        resp = httpx.post(
            f"{ZOHO_API_BASE}/bills",
            headers=_headers(),
            params=_org_params(),
            json=payload,
            timeout=30,
        )

    resp.raise_for_status()
    result = resp.json()
    logger.info(
        "Created Zoho bill %s (bill_id=%s)",
        invoice_number,
        result.get("bill", {}).get("bill_id"),
    )
    return result
