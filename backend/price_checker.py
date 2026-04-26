"""
price_checker.py — Price/MRP change detection and history tracking.

Status flags:
  NORMAL       — No change from last known price
  PRICE_CHANGE — Rate or MRP differs from last stored value
  NEW_PRODUCT  — No mapping found (first time seeing this product)
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from backend.db import price_history, product_cache

logger = logging.getLogger(__name__)


class ItemStatus(str, Enum):
    NORMAL = "normal"
    PRICE_CHANGE = "price_change"
    NEW_PRODUCT = "new_product"


def check_price_change(
    zoho_item_id: str,
    current_rate: float,
    current_mrp: Optional[float] = None,
) -> tuple[ItemStatus, dict]:
    """
    Compare current price against the most recent price history entry.

    Returns:
        (status, detail_dict)
        detail_dict contains previous_rate and previous_mrp when relevant.
    """
    # Get the most recent price history record for this item
    last = price_history().find_one(
        {"zoho_item_id": zoho_item_id},
        sort=[("date", -1)],
    )

    if last is None:
        # First time we're seeing this zoho item — treat as normal (it IS mapped)
        return ItemStatus.NORMAL, {}

    prev_rate = last.get("rate")
    prev_mrp = last.get("mrp")

    rate_changed = prev_rate is not None and abs(prev_rate - current_rate) > 0.001
    mrp_changed = (
        prev_mrp is not None
        and current_mrp is not None
        and abs(prev_mrp - current_mrp) > 0.001
    )

    if rate_changed or mrp_changed:
        return ItemStatus.PRICE_CHANGE, {
            "previous_rate": prev_rate,
            "previous_mrp": prev_mrp,
        }

    return ItemStatus.NORMAL, {}


def save_price_history(
    zoho_item_id: str,
    rate: float,
    mrp: Optional[float] = None,
) -> None:
    """
    Insert a new price history record for a Zoho item.
    Called after a bill is confirmed.
    """
    price_history().insert_one(
        {
            "zoho_item_id": zoho_item_id,
            "rate": rate,
            "mrp": mrp,
            "date": datetime.now(timezone.utc),
        }
    )
    logger.debug("Saved price history for item %s: rate=%s mrp=%s", zoho_item_id, rate, mrp)


def get_item_from_cache(zoho_item_id: str) -> Optional[dict]:
    """Look up a Zoho item in the local product_cache."""
    return product_cache().find_one(
        {"zoho_item_id": zoho_item_id}, {"_id": 0}
    )
