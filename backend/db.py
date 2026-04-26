"""
db.py — MongoDB client and collection accessors.
MongoDB is used as a cache/memory layer; Zoho Books is the source of truth.
"""

import os
import certifi
from pymongo import MongoClient
from pymongo.collection import Collection


_client: MongoClient | None = None
_db = None


def get_db():
    global _client, _db
    if _client is None:
        mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        _client = MongoClient(mongo_uri, tlsCAFile=certifi.where())
        _db = _client["billsync"]
        _ensure_indexes()
    return _db


def _ensure_indexes():
    db = _db
    db["product_mapping"].create_index(
        [("vendor", 1), ("vendor_product_name", 1)], unique=True
    )
    db["invoices"].create_index("invoice_number", unique=True)
    db["price_history"].create_index([("zoho_item_id", 1), ("date", -1)])
    db["product_cache"].create_index("zoho_item_id", unique=True)


# ── Collection helpers ──────────────────────────────────────────────────────

def product_cache() -> Collection:
    """Zoho items cached locally.
    Schema: { zoho_item_id, name, rate, mrp, last_synced_at }
    """
    return get_db()["product_cache"]


def product_mapping() -> Collection:
    """Vendor product name → Zoho item mapping.
    Schema: { vendor, vendor_product_name, zoho_item_id, zoho_item_name }
    """
    return get_db()["product_mapping"]


def price_history() -> Collection:
    """Historical price records per Zoho item.
    Schema: { zoho_item_id, price, mrp, date }
    """
    return get_db()["price_history"]


def invoices() -> Collection:
    """Processed invoice records.
    Schema: { invoice_number, vendor, date, status, zoho_bill_id }
    """
    return get_db()["invoices"]
