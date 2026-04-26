"""
matcher.py — Product mapping engine.

Logic:
  1. Check MongoDB product_mapping for an existing exact match.
  2. If not found, run rapidfuzz against the product_cache (Zoho items).
  3. Return top-N candidates for the user to choose from.
  4. After the user confirms, save the mapping so it's reused next time.
"""

import logging
from typing import Optional
from rapidfuzz import process, fuzz
from backend.db import product_mapping, product_cache

logger = logging.getLogger(__name__)

VENDOR = "Milky Mist"
TOP_N = 5
MATCH_THRESHOLD = 60  # Minimum score to include a candidate


def get_mapping(vendor_product_name: str) -> Optional[dict]:
    """
    Look up an existing mapping for a vendor product name.

    Returns:
        { zoho_item_id, zoho_item_name } or None
    """
    doc = product_mapping().find_one(
        {"vendor": VENDOR, "vendor_product_name": vendor_product_name},
        {"_id": 0, "zoho_item_id": 1, "zoho_item_name": 1},
    )
    return doc


def fuzzy_match(vendor_product_name: str) -> list[dict]:
    """
    Run rapidfuzz against locally-cached Zoho items.

    Returns a list of up to TOP_N candidates:
        [ { zoho_item_id, zoho_item_name, score }, ... ]
    """
    # Load all cached Zoho items
    items = list(product_cache().find({}, {"_id": 0, "zoho_item_id": 1, "name": 1}))
    if not items:
        logger.warning("product_cache is empty — run Zoho sync first")
        return []

    choices = {item["zoho_item_id"]: item["name"] for item in items}

    results = process.extract(
        vendor_product_name,
        choices,
        scorer=fuzz.token_set_ratio,
        limit=TOP_N,
    )

    candidates = []
    for name, score, zoho_item_id in results:
        if score >= MATCH_THRESHOLD:
            candidates.append(
                {
                    "zoho_item_id": zoho_item_id,
                    "zoho_item_name": name,
                    "score": round(score, 1),
                }
            )

    logger.debug(
        "Fuzzy match '%s' → %d candidates (threshold=%d)",
        vendor_product_name,
        len(candidates),
        MATCH_THRESHOLD,
    )
    return candidates


def save_mapping(vendor_product_name: str, zoho_item_id: str, zoho_item_name: str) -> None:
    """
    Upsert a vendor_product_name → Zoho item mapping.
    """
    product_mapping().update_one(
        {"vendor": VENDOR, "vendor_product_name": vendor_product_name},
        {
            "$set": {
                "vendor": VENDOR,
                "vendor_product_name": vendor_product_name,
                "zoho_item_id": zoho_item_id,
                "zoho_item_name": zoho_item_name,
            }
        },
        upsert=True,
    )
    logger.info("Saved mapping: '%s' → '%s' (%s)", vendor_product_name, zoho_item_name, zoho_item_id)
