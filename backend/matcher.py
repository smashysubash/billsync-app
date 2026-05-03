"""
matcher.py — Product mapping engine.

Logic:
  1. Check MongoDB product_mapping for an existing exact match.
  2. If not found, run rapidfuzz against the product_cache (Zoho items).
  3. Return top-N candidates for the user to choose from.
  4. After the user confirms, save the mapping so it's reused next time.
"""

import logging
import re
from rapidfuzz import process, fuzz, utils
from db import product_mapping, product_cache
from typing import Optional

logger = logging.getLogger(__name__)

VENDOR = "Milky Mist"
TOP_N = None
MATCH_THRESHOLD = 0  # Include all items


def product_processor(s: str) -> str:
    """
    Normalize product names for better matching:
    - Lowercase
    - Normalize units (gm, gms -> g)
    - Remove non-alphanumeric characters
    """
    if not s:
        return ""
    s = str(s).lower()
    # Normalize grams: 100GM, 100 gm, 100gms -> 100g
    s = re.sub(r"(\d+)\s*(gms?|gm|g)\b", r"\1g", s)
    # Normalize milliliters: 500 ml, 500ML -> 500ml
    s = re.sub(r"(\d+)\s*(mls?|ml)\b", r"\1ml", s)
    # Standard rapidfuzz cleaning (removes punctuation, etc.)
    return utils.default_process(s)


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

    Returns a list of candidates sorted by score:
        [ { zoho_item_id, zoho_item_name, score }, ... ]
    """
    # Load all cached Zoho items
    items = list(product_cache().find({}, {"_id": 0, "zoho_item_id": 1, "name": 1, "sku": 1}))
    if not items:
        logger.warning("product_cache is empty — run Zoho sync first")
        return []

    choices = {item["zoho_item_id"]: item["name"] for item in items}
    sku_map = {item["zoho_item_id"]: item.get("sku") for item in items}

    # Use WRatio for better overall matching performance
    # and our custom processor for unit normalization.
    results = process.extract(
        vendor_product_name,
        choices,
        scorer=fuzz.WRatio,
        processor=product_processor,
        limit=TOP_N,
    )

    candidates = []
    for name, score, zoho_item_id in results:
        candidates.append(
            {
                "zoho_item_id": zoho_item_id,
                "zoho_item_name": name,
                "sku": sku_map.get(zoho_item_id),
                "score": round(score, 1),
            }
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
