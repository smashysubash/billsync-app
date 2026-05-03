"""
zoho.py — Zoho Books API client + OAuth 2.0 helpers.

Credential priority:
  1. MongoDB zoho_config collection (set via the /zoho/connect UI flow)
  2. Environment variables ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET /
     ZOHO_REFRESH_TOKEN / ZOHO_ORGANIZATION_ID  (legacy / Docker .env)

OAuth flow (automated):
  Frontend POSTs client_id + client_secret → backend returns an auth URL
  → user approves in browser → Zoho redirects to /zoho/callback?code=...
  → backend exchanges code for tokens → stored in MongoDB → done.
"""

import os
import json
import logging
from datetime import datetime, timezone
import httpx
from db import product_cache, zoho_config

logger = logging.getLogger(__name__)

ZOHO_TOKEN_URL    = "https://accounts.zoho.in/oauth/v2/token"
ZOHO_AUTH_URL     = "https://accounts.zoho.in/oauth/v2/auth"
ZOHO_API_BASE     = "https://www.zohoapis.in/books/v3"
ZOHO_SCOPE        = "ZohoBooks.fullaccess.all"

_access_token: str | None = None


# ── Credential loading ────────────────────────────────────────────────────────

def _load_config() -> dict | None:
    """
    Load OAuth credentials from MongoDB, falling back to env vars.
    Returns a dict with client_id, client_secret, refresh_token,
    organization_id — or None if not configured at all.
    """
    # 1. Try DB
    doc = zoho_config().find_one({"key": "main"})
    if doc and doc.get("client_id"):
        return {
            "client_id":       doc["client_id"],
            "client_secret":   doc["client_secret"],
            "refresh_token":   doc.get("refresh_token", ""),
            "organization_id": doc.get("organization_id", ""),
        }

    # 2. Fall back to env vars
    client_id     = os.environ.get("ZOHO_CLIENT_ID", "")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
    refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN", "")
    org_id        = os.environ.get("ZOHO_ORGANIZATION_ID", "")

    if client_id and client_secret and refresh_token:
        return {
            "client_id":       client_id,
            "client_secret":   client_secret,
            "refresh_token":   refresh_token,
            "organization_id": org_id,
        }

    return None


def save_config(client_id: str, client_secret: str,
                refresh_token: str, organization_id: str = "") -> None:
    """Persist OAuth credentials to MongoDB."""
    zoho_config().update_one(
        {"key": "main"},
        {"$set": {
            "key":             "main",
            "client_id":       client_id,
            "client_secret":   client_secret,
            "refresh_token":   refresh_token,
            "organization_id": organization_id,
            "updated_at":      datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    logger.info("Zoho credentials saved to DB")


def get_connection_status() -> dict:
    """Return the current Zoho connection state for the frontend."""
    cfg = _load_config()
    if not cfg:
        return {"connected": False, "organization_id": None, "has_client_id": False}

    # Check if there's a partial config (client creds but no refresh token yet)
    doc = zoho_config().find_one({"key": "main"}) or {}
    return {
        "connected":       bool(cfg.get("refresh_token")),
        "organization_id": cfg.get("organization_id") or None,
        "has_client_id":   bool(cfg.get("client_id")),
        "client_id_hint":  (cfg["client_id"][:8] + "…") if cfg.get("client_id") else None,
    }


# ── OAuth authorization flow ──────────────────────────────────────────────────

def build_auth_url(client_id: str, redirect_uri: str) -> str:
    """Return the Zoho OAuth consent-screen URL."""
    params = (
        f"response_type=code"
        f"&client_id={client_id}"
        f"&scope={ZOHO_SCOPE}"
        f"&redirect_uri={redirect_uri}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return f"{ZOHO_AUTH_URL}?{params}"


def exchange_code_for_tokens(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict:
    """
    Exchange an authorization code for access + refresh tokens.
    Saves the refresh token and organization_id to MongoDB.
    Returns the token response dict.
    """
    resp = httpx.post(
        ZOHO_TOKEN_URL,
        params={
            "grant_type":    "authorization_code",
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  redirect_uri,
            "code":          code,
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    if "refresh_token" not in data:
        raise RuntimeError(f"Token exchange failed — no refresh_token in response: {data}")

    # Fetch organization_id automatically
    org_id = _fetch_org_id(data["access_token"])

    save_config(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=data["refresh_token"],
        organization_id=org_id,
    )

    logger.info("Zoho OAuth complete — org_id=%s", org_id)
    return {**data, "organization_id": org_id}


def _fetch_org_id(access_token: str) -> str:
    """Fetch the first Zoho Books organization ID using a fresh access token."""
    try:
        resp = httpx.get(
            f"{ZOHO_API_BASE}/organizations",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        orgs = resp.json().get("organizations", [])
        return str(orgs[0]["organization_id"]) if orgs else ""
    except Exception as e:
        logger.warning("Could not auto-fetch org_id: %s", e)
        return ""


# ── Token management ─────────────────────────────────────────────────────────

def refresh_access_token() -> str:
    """Exchange the stored refresh token for a new access token."""
    global _access_token
    cfg = _load_config()
    if not cfg:
        raise RuntimeError("Zoho not configured. Complete the OAuth setup first.")

    resp = httpx.post(
        ZOHO_TOKEN_URL,
        params={
            "grant_type":    "refresh_token",
            "client_id":     cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": cfg["refresh_token"],
        },
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error("Zoho token refresh failed (HTTP %s): %s", resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Zoho token refresh failed: {data}")

    _access_token = data["access_token"]
    logger.info("Zoho access token refreshed")
    return _access_token


def _token() -> str:
    global _access_token
    if not _access_token:
        refresh_access_token()
    return _access_token


def _headers() -> dict:
    return {"Authorization": f"Zoho-oauthtoken {_token()}"}


def _org_params() -> dict:
    cfg = _load_config()
    return {"organization_id": cfg["organization_id"]} if cfg else {}


# ── Item sync ────────────────────────────────────────────────────────────────

def fetch_items() -> int:
    """Fetch all active items from Zoho Books → replace local product_cache."""
    all_items = []
    page = 1

    while True:
        resp = httpx.get(
            f"{ZOHO_API_BASE}/items",
            headers=_headers(),
            params={**_org_params(), "page": page, "per_page": 200, "filter_by": "Status.Active"},
            timeout=30,
        )
        if resp.status_code == 401:
            refresh_access_token()
            resp = httpx.get(
                f"{ZOHO_API_BASE}/items",
                headers=_headers(),
                params={**_org_params(), "page": page, "per_page": 200, "filter_by": "Status.Active"},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        all_items.extend(items)

        if not data.get("page_context", {}).get("has_more_page", False):
            break
        page += 1

    col = product_cache()
    col.delete_many({})
    if all_items:
        now = datetime.now(timezone.utc)
        col.insert_many([
            {
                "zoho_item_id":          str(item["item_id"]),
                "name":                  item["name"],
                "sku":                   item.get("sku", ""),
                "rate":                  item.get("rate", 0.0),
                "purchase_account_id":   item.get("purchase_account_id", ""),
                "purchase_account_name": item.get("purchase_account_name", ""),
                "is_inventory":          item.get("is_inventory_tracked", False),
                "mrp":                   item.get("custom_fields_hash", {}).get("cf_mrp"),
                "last_synced_at":        now,
            }
            for item in all_items
        ])

    logger.info("Zoho sync complete — %d items cached", len(all_items))
    return len(all_items)


# ── Bill creation ────────────────────────────────────────────────────────────

def create_bill(
    vendor_id: str,
    invoice_number: str,
    invoice_date: str,
    line_items: list[dict],
) -> dict:
    """Create a purchase bill in Zoho Books with automatic tax mapping."""
    # Fetch taxes to find matching IDs
    all_taxes = fetch_taxes()
   
    def find_tax_info(pct: float) -> dict:
        # Match by percentage (round to 2 decimals to avoid floating point issues)
        for t in all_taxes:
            t_pct = t.get("tax_percentage") or t.get("tax_group_percentage") or 0.0
            if abs(float(t_pct) - pct) < 0.01:
                return {
                    "tax_id":   t.get("tax_id"),
                    "tax_type": t.get("tax_type", "tax")
                }
        
        # Fallback: try to match by common name if pct is standard
        name_map = {18.0: "GST18", 5.0: "GST5", 12.0: "GST12", 0.0: "GST0"}
        target_name = name_map.get(round(float(pct), 2))
        if target_name:
            for t in all_taxes:
                if t.get("tax_name") == target_name:
                    return {"tax_id": t["tax_id"], "tax_type": t.get("tax_type", "tax")}
                    
        logger.warning("No matching Zoho tax found for %s%%", pct)
        return {}

    line_items_payload = []
    for li in line_items:
        tax_info = find_tax_info(li.get("cgst_pct", 0) + li.get("sgst_pct", 0))
        item = {
            "item_id":     li["item_id"],
            **({"account_id": li["account_id"]} if li.get("account_id") else {}),
            "name":        li["name"],
            # "description": li.get("description", ""),
            "quantity":    li["quantity"],
            "rate":        li["rate"],
            "discount":    f"{li.get('discount', 0)}%",
            **tax_info
        }
        line_items_payload.append(item)

    payload = {
        "vendor_id":        vendor_id,
        "bill_number":      invoice_number,
        "reference_number": invoice_number,
        "date":             invoice_date,
        "is_inclusive_tax": False,
        "discount_type":    "item_level",
        "line_items":       line_items_payload,
    }

    logger.debug("Zoho Create Bill Payload: %s", json.dumps(payload, indent=2))
    resp = httpx.post(
        f"{ZOHO_API_BASE}/bills",
        headers=_headers(),
        params=_org_params(),
        json=payload,
        timeout=30,
    )
    resp_data = resp.json()
    logger.debug("Zoho Create Bill Response: %s", resp_data)
    
    if resp.status_code == 401:
        refresh_access_token()
        resp = httpx.post(
            f"{ZOHO_API_BASE}/bills",
            headers=_headers(),
            params=_org_params(),
            json=payload,
            timeout=30,
        )

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("Zoho API error: %s | Response: %s", e, resp.text)
        raise

    result = resp.json()
    logger.info("Created Zoho bill %s (bill_id=%s)",
                invoice_number, result.get("bill", {}).get("bill_id"))
    return result


def fetch_taxes() -> list[dict]:
    """Fetch available tax rates and tax groups from Zoho Books."""
    resp = httpx.get(
        f"{ZOHO_API_BASE}/settings/taxes",
        headers=_headers(),
        params=_org_params(),
        timeout=15,
    )
    if resp.status_code == 401:
        refresh_access_token()
        resp = httpx.get(
            f"{ZOHO_API_BASE}/settings/taxes",
            headers=_headers(),
            params=_org_params(),
            timeout=15,
        )
    resp.raise_for_status()
    data = resp.json()
    taxes = data.get("taxes", [])
    logger.info("Fetched %d taxes/groups from Zoho", len(taxes))
    return taxes
