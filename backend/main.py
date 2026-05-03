"""
main.py — BillSync FastAPI application.

Endpoints:
  POST /upload-invoice/     Upload PDF, extract text
  POST /process-invoice/    Parse + match + flag → returns review payload
  POST /confirm-invoice/    User confirmed → create Zoho bill
  POST /mappings/           Save a user-confirmed product mapping
  GET  /zoho/sync-items/    Manually trigger Zoho item sync
"""

import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import fitz  # PyMuPDF
import pdfplumber
from pdf2image import convert_from_path
from paddleocr import PaddleOCR

from backend.db import invoices, product_mapping
from backend.matcher import fuzzy_match, get_mapping, save_mapping
from backend.parser import extract_invoice_metadata, parse_invoice_lines
from backend.price_checker import (
    ItemStatus,
    check_price_change,
    get_item_from_cache,
    save_price_history,
)

# Try importing Zoho module — allow startup without credentials (graceful degradation)
try:
    from backend.zoho import (
        create_bill, fetch_items, refresh_access_token,
        build_auth_url, exchange_code_for_tokens,
        get_connection_status, save_config, _load_config,
    )
    ZOHO_ENABLED = True
except Exception:
    ZOHO_ENABLED = False

# ── Logging Configuration ───────────────────────────────────────────────────

# Set root logger to INFO to avoid noise from libraries like pdfminer/pymongo
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s | %(name)-14s | %(message)s",
)

# Enable DEBUG specifically for our application code
logger = logging.getLogger("backend")
logger.setLevel(logging.DEBUG)

# Explicitly silence noisy third-party libraries even if they use the root logger
logging.getLogger("pdfminer").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

VENDOR_ZOHO_ID = os.environ.get("VENDOR_ZOHO_ID")


# ── Scheduler ────────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()


def _weekly_sync():
    if ZOHO_ENABLED:
        try:
            count = fetch_items()
            logger.info("[APScheduler] Weekly Zoho sync complete — %d items", count)
        except Exception as e:
            logger.error("[APScheduler] Weekly Zoho sync failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler on app startup
    scheduler.add_job(_weekly_sync, "interval", weeks=1, id="weekly_zoho_sync")
    scheduler.start()
    logger.info("APScheduler started — weekly Zoho sync scheduled")
    yield
    scheduler.shutdown()


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BillSync API",
    description="Milky Mist invoice → Zoho Books purchase bill automation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://192.168.1.50:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── PDF helpers ───────────────────────────────────────────────────────────────

def detect_pdf_type(file_path: str) -> str:
    """Return 'text' if text-based, 'image' if image/scanned."""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                if page.extract_text():
                    return "text"
        return "image"
    except Exception:
        return "image"


def extract_text_pdfplumber(file_path: str) -> Optional[str]:
    try:
        with pdfplumber.open(file_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return text.strip() or None
    except Exception as e:
        logger.warning("pdfplumber failed: %s", e)
        return None


def extract_text_pymupdf(file_path: str) -> Optional[str]:
    try:
        doc = fitz.open(file_path)
        text = "\n".join(page.get_text() for page in doc)
        return text.strip() or None
    except Exception as e:
        logger.warning("PyMuPDF failed: %s", e)
        return None


def extract_text_ocr(file_path: str) -> Optional[str]:
    try:
        images = convert_from_path(file_path)
        ocr = PaddleOCR(use_angle_cls=True, lang="en")
        all_blocks = []
        for img in images:
            result = ocr.ocr(img, cls=True)
            for line in result:
                for word in line:
                    # word structure: [coordinates, (text, confidence)]
                    # coordinates: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    coords = word[0]
                    text = word[1][0]
                    # Extract Y-coordinate (use top-left y-coordinate for sorting)
                    y_coord = coords[0][1] if coords else 0
                    all_blocks.append((y_coord, text))
        
        # Sort by Y-coordinate (top-to-bottom reading order)
        all_blocks.sort(key=lambda x: x[0])
        lines = [text for _, text in all_blocks]
        
        return "\n".join(lines).strip() or None
    except Exception as e:
        logger.warning("PaddleOCR failed: %s", e)
        return None


# ── Pydantic models ──────────────────────────────────────────────────────────

class MappingRequest(BaseModel):
    vendor_product_name: str
    zoho_item_id: str
    zoho_item_name: str


class ConfirmLineItem(BaseModel):
    index: int
    product_name: str          # vendor product name
    zoho_item_id: str
    zoho_item_name: str
    qty: float
    rate: float
    amount: float
    cgst_pct: float = 0.0
    sgst_pct: float = 0.0
    disc_pct: float = 0.0


class ConfirmInvoiceRequest(BaseModel):
    invoice_number: str
    invoice_date: str
    vendor_zoho_id: Optional[str] = None
    file_path: Optional[str] = None
    line_items: list[ConfirmLineItem]


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/upload-invoice/", tags=["Invoice"])
async def upload_invoice(file: UploadFile = File(...)):
    """
    Upload a PDF invoice. Returns extracted text and file path.
    The text can then be sent to /process-invoice/.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Prefix filename with timestamp + UUID to prevent collision on concurrent uploads
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    uuid_prefix = uuid.uuid4().hex[:8]
    prefixed_filename = f"{timestamp}_{uuid_prefix}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, prefixed_filename)
    with open(file_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    pdf_type = detect_pdf_type(file_path)
    text: Optional[str] = None

    if pdf_type == "text":
        text = extract_text_pdfplumber(file_path)
        if not text:
            text = extract_text_pymupdf(file_path)
    else:
        text = extract_text_ocr(file_path)

    if not text:
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from the PDF. Check if it is a valid Milky Mist invoice.",
        )

    return {
        "filename": file.filename,
        "saved_filename": prefixed_filename,
        "file_path": file_path,
        "pdf_type": pdf_type,
        "text": text,
    }


@app.post("/process-invoice/", tags=["Invoice"])
async def process_invoice(payload: dict):
    """
    Parse extracted invoice text into line items and run product matching.

    Expects: { "text": "<raw text>", "file_path": "<path>" }

    Returns a review payload with:
      - invoice metadata
      - line items, each annotated with:
          - matched zoho item (or fuzzy candidates)
          - status: normal / price_change / new_product
    """
    text: str = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="'text' field is required.")

    # Extract metadata
    meta = extract_invoice_metadata(text)

    # Check for duplicate invoice
    if meta["invoice_number"]:
        existing = invoices().find_one({"invoice_number": meta["invoice_number"]})
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Invoice {meta['invoice_number']} has already been processed (status: {existing.get('status', 'unknown')}).",
            )

    # Parse line items — pass file_path to enable table-based extraction
    file_path: str = payload.get("file_path", "")
    raw_items = parse_invoice_lines(text, file_path=file_path or None)
    if not raw_items:
        raise HTTPException(
            status_code=422,
            detail="No line items found. The invoice format may not match the expected layout.",
        )

    # Match each line item
    review_items = []
    for item in raw_items:
        vendor_name = item["product_name"]

        # 1. Check existing mapping (Memory first)
        mapping = get_mapping(vendor_name)
        
        # 2. Run fuzzy matching (Always needed for the candidates picker)
        candidates = fuzzy_match(vendor_name)
        
        zoho_item_id = None
        zoho_item_name = None
        is_mapped = False

        if mapping:
            zoho_item_id = mapping["zoho_item_id"]
            zoho_item_name = mapping["zoho_item_name"]
            is_mapped = True
        elif candidates and candidates[0]["score"] >= 100:
            # 3. Auto-choose 100% matches
            zoho_item_id = candidates[0]["zoho_item_id"]
            zoho_item_name = candidates[0]["zoho_item_name"]
            is_mapped = True
            # Save this 100% match to mapping table for future instant lookup
            save_mapping(vendor_name, zoho_item_id, zoho_item_name)
        
        if is_mapped:
            status, price_detail = check_price_change(zoho_item_id, item["rate"])
            review_items.append({
                **item,
                "zoho_item_id": zoho_item_id,
                "zoho_item_name": zoho_item_name,
                "status": status,
                "price_detail": price_detail,
                "candidates": candidates,
                "mapped": True,
            })
        else:
            # No mapping found and no 100% match — user must decide
            review_items.append({
                **item,
                "zoho_item_id": None,
                "zoho_item_name": None,
                "status": ItemStatus.NEW_PRODUCT,
                "price_detail": {},
                "candidates": candidates,
                "mapped": False,
            })

    # Calculate totals
    subtotal = sum(item["qty"] * item["rate"] for item in review_items)
    discount_total = sum(
        item["qty"] * item["rate"] * item["disc_pct"] / 100
        for item in review_items
    )
    tax_total = sum(
        item["qty"] * item["rate"] * (item["cgst_pct"] + item["sgst_pct"]) / 100
        for item in review_items
    )
    grand_total = subtotal - discount_total + tax_total

    return {
        "meta": meta,
        "items": review_items,
        "total_items": len(review_items),
        "unmapped_count": sum(1 for i in review_items if not i["mapped"]),
        "totals": {
            "subtotal": round(subtotal, 2),
            "discount_total": round(discount_total, 2),
            "tax_total": round(tax_total, 2),
            "grand_total": round(grand_total, 2),
        },
        "file_path": payload.get("file_path"),
    }


@app.post("/confirm-invoice/", tags=["Invoice"])
async def confirm_invoice(req: ConfirmInvoiceRequest):
    """
    User has reviewed all line items and confirmed the invoice.
    Creates a purchase bill in Zoho Books and saves the invoice record.
    """
    logger.debug("Received confirm-invoice request: %s", req.model_dump())
    # Final duplicate guard
    if req.invoice_number:
        existing = invoices().find_one({"invoice_number": req.invoice_number})
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Invoice {req.invoice_number} already exists.",
            )

    zoho_bill_id = None
    zoho_error = None

    # Use VENDOR_ZOHO_ID from environment (server-side), not from frontend
    vendor_id = VENDOR_ZOHO_ID or req.vendor_zoho_id
    
    if ZOHO_ENABLED and vendor_id:
        try:
            zoho_line_items = []
            for li in req.line_items:
                # Attempt to get the purchase account ID from cache if item exists
                cached = get_item_from_cache(li.zoho_item_id) if li.zoho_item_id else None
                acc_id = cached.get("purchase_account_id") if cached else None
                
                zoho_line_items.append({
                    "item_id":     li.zoho_item_id,
                    "account_id":  None if li.zoho_item_id else acc_id,
                    "name":        li.zoho_item_name,
                    "description": f"Extracted from invoice: {li.product_name}",
                    "quantity":    li.qty,
                    "rate":        li.rate,
                    "cgst_pct":    li.cgst_pct,
                    "sgst_pct":    li.sgst_pct,
                    "discount":    li.disc_pct,
                })

            result = create_bill(
                vendor_id=vendor_id,
                invoice_number=req.invoice_number,
                invoice_date=req.invoice_date,
                line_items=zoho_line_items,
            )
            zoho_bill_id = result.get("bill", {}).get("bill_id")
        except Exception as e:
            logger.error("Zoho bill creation failed: %s", e)
            zoho_error = str(e)

    # Save invoice record
    invoices().insert_one({
        "invoice_number": req.invoice_number,
        "vendor": "Milky Mist",
        "date": req.invoice_date,
        "status": "confirmed" if zoho_bill_id else "pending_zoho",
        "zoho_bill_id": zoho_bill_id,
        "created_at": datetime.now(timezone.utc),
    })

    # Save price history for all mapped items
    for li in req.line_items:
        if li.zoho_item_id:
            cached = get_item_from_cache(li.zoho_item_id)
            mrp = cached.get("mrp") if cached else None
            save_price_history(li.zoho_item_id, li.rate, mrp)

    # Cleanup local PDF if provided
    if req.file_path and os.path.exists(req.file_path):
        try:
            os.remove(req.file_path)
            logger.info("Deleted local PDF: %s", req.file_path)
        except Exception as e:
            logger.error("Failed to delete local PDF %s: %s", req.file_path, e)

    return {
        "success": True,
        "invoice_number": req.invoice_number,
        "zoho_bill_id": zoho_bill_id,
        "zoho_error": zoho_error,
    }


@app.post("/mappings/", tags=["Mappings"])
async def create_mapping(req: MappingRequest):
    """Save a user-confirmed vendor→Zoho product mapping."""
    try:
        save_mapping(req.vendor_product_name, req.zoho_item_id, req.zoho_item_name)
        return {"success": True, "message": f"Mapping saved for '{req.vendor_product_name}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mappings/{vendor_product_name}", tags=["Mappings"])
async def get_product_mapping(vendor_product_name: str):
    """Look up an existing product mapping by vendor product name."""
    mapping = get_mapping(vendor_product_name)
    if not mapping:
        raise HTTPException(status_code=404, detail="No mapping found.")
    return mapping

@app.get("/zoho/status", tags=["Zoho"])
async def zoho_status():
    """Return current Zoho connection state."""
    if not ZOHO_ENABLED:
        return {"connected": False, "organization_id": None, "has_client_id": False}
    return get_connection_status()


class ZohoConnectRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str  # e.g. "http://localhost:9001/zoho/callback"


@app.post("/zoho/connect", tags=["Zoho"])
async def zoho_connect(req: ZohoConnectRequest):
    """
    Step 1 of OAuth: store client credentials temporarily and return the
    Zoho authorization URL for the user to open in their browser.
    """
    if not ZOHO_ENABLED:
        raise HTTPException(status_code=503, detail="Zoho module unavailable.")

    # Persist client creds (without refresh_token yet) so the callback can use them
    save_config(
        client_id=req.client_id,
        client_secret=req.client_secret,
        refresh_token="",  # not yet acquired
        organization_id="",
    )

    auth_url = build_auth_url(req.client_id, req.redirect_uri)
    return {"auth_url": auth_url}


@app.get("/zoho/callback", tags=["Zoho"])
async def zoho_callback(code: str, redirect_uri: str = "http://localhost:9001/zoho/callback"):
    """
    Step 2 of OAuth: Zoho redirects here with ?code=...
    The backend exchanges the code for tokens and saves them.
    Returns an HTML page that closes itself (popup flow).
    """
    if not ZOHO_ENABLED:
        raise HTTPException(status_code=503, detail="Zoho module unavailable.")

    cfg = _load_config()
    if not cfg or not cfg.get("client_id"):
        raise HTTPException(status_code=400, detail="No client credentials found. Call /zoho/connect first.")

    try:
        result = exchange_code_for_tokens(
            client_id=cfg["client_id"],
            client_secret=cfg["client_secret"],
            code=code,
            redirect_uri=redirect_uri,
        )
        org_id = result.get("organization_id", "")
        html = f"""
        <!DOCTYPE html><html><body style="font-family:sans-serif;padding:40px;text-align:center">
        <h2 style="color:#16a34a">&#10003; Zoho Books connected!</h2>
        <p>Organization ID: <strong>{org_id or 'see settings'}</strong></p>
        <p>You can close this window.</p>
        <script>setTimeout(() => window.close(), 2000);</script>
        </body></html>
        """
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html)
    except Exception as e:
        logger.error("OAuth callback failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {e}")


class ZohoSaveConfigRequest(BaseModel):
    client_id: str
    client_secret: str
    refresh_token: str
    organization_id: Optional[str] = ""


@app.post("/zoho/save-config", tags=["Zoho"])
async def zoho_save_config(req: ZohoSaveConfigRequest):
    """Manually save Zoho credentials (alternative to the OAuth flow)."""
    if not ZOHO_ENABLED:
        raise HTTPException(status_code=503, detail="Zoho module unavailable.")
    save_config(req.client_id, req.client_secret, req.refresh_token, req.organization_id or "")
    return {"success": True, "message": "Zoho credentials saved."}


@app.get("/zoho/sync-items/", tags=["Zoho"])
async def sync_zoho_items():
    """Manually trigger a full Zoho Books item sync."""
    if not ZOHO_ENABLED:
        raise HTTPException(status_code=503, detail="Zoho module unavailable.")
    cfg = _load_config()
    if not cfg:
        raise HTTPException(
            status_code=503,
            detail="Zoho not connected. Complete OAuth setup via Settings.",
        )
    try:
        count = fetch_items()
        return {"success": True, "synced_items": count}
    except Exception as e:
        logger.error("Zoho sync failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Zoho sync failed: {e}")


@app.get("/zoho/items/", tags=["Zoho"])
async def search_zoho_items(q: str = "", limit: int = 10):
    """
    Search cached Zoho items by name or SKU (real-time search for product picker).
    
    Args:
        q: Search query (product name or SKU)
        limit: Max number of results (default 10)
    
    Returns:
        List of items: [ { zoho_item_id, name, sku, rate, score }, ... ]
    """
    if not ZOHO_ENABLED:
        raise HTTPException(status_code=503, detail="Zoho module unavailable.")
    
    # If no query, return empty list
    if not q or not q.strip():
        return []
    
    try:
        from backend.db import product_cache
        
        q_lower = q.lower().strip()
        
        # Search in product_cache: name or sku field (case-insensitive)
        results = list(
            product_cache().find(
                {
                    "$or": [
                        {"name": {"$regex": q_lower, "$options": "i"}},
                        {"sku": {"$regex": q_lower, "$options": "i"}},
                    ]
                },
                {"_id": 0, "zoho_item_id": 1, "name": 1, "sku": 1, "rate": 1},
            ).limit(limit)
        )
        
        # Calculate fuzzy match score for better sorting
        from rapidfuzz import fuzz
        
        scored = []
        for item in results:
            score = fuzz.token_set_ratio(q_lower, item.get("name", "").lower())
            scored.append({
                **item,
                "score": round(score, 1),
            })
        
        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        return scored
    except Exception as e:
        logger.error("Zoho items search failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@app.get("/config/", tags=["System"])
async def config():
    """Return app configuration status (Zoho setup, vendor ID configured, etc)."""
    return {
        "zoho_enabled": ZOHO_ENABLED,
        "vendor_zoho_id_configured": bool(VENDOR_ZOHO_ID),
        "upload_dir": UPLOAD_DIR,
    }


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "zoho_enabled": ZOHO_ENABLED}
