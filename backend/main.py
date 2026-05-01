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

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    allow_origins=["*"],
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
        lines = []
        for img in images:
            result = ocr.ocr(img, cls=True)
            for line in result:
                for word in line:
                    lines.append(word[1][0])
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


class ConfirmInvoiceRequest(BaseModel):
    invoice_number: str
    invoice_date: str
    vendor_zoho_id: Optional[str] = None
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

    file_path = os.path.join(UPLOAD_DIR, file.filename)
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

        # Try existing mapping
        mapping = get_mapping(vendor_name)
        # Always get candidates so user can change/correct the mapping
        candidates = fuzzy_match(vendor_name)
        
        if mapping:
            zoho_item_id = mapping["zoho_item_id"]
            zoho_item_name = mapping["zoho_item_name"]
            status, price_detail = check_price_change(
                zoho_item_id, item["rate"]
            )
            review_items.append({
                **item,
                "zoho_item_id": zoho_item_id,
                "zoho_item_name": zoho_item_name,
                "status": status,
                "price_detail": price_detail,
                "candidates": candidates, # Include candidates even if mapped
                "mapped": True,
            })
        else:
            # Fuzzy match candidates for user to pick from
            review_items.append({
                **item,
                "zoho_item_id": None,
                "zoho_item_name": None,
                "status": ItemStatus.NEW_PRODUCT,
                "price_detail": {},
                "candidates": candidates,
                "mapped": False,
            })

    return {
        "meta": meta,
        "items": review_items,
        "total_items": len(review_items),
        "unmapped_count": sum(1 for i in review_items if not i["mapped"]),
    }


@app.post("/confirm-invoice/", tags=["Invoice"])
async def confirm_invoice(req: ConfirmInvoiceRequest):
    """
    User has reviewed all line items and confirmed the invoice.
    Creates a purchase bill in Zoho Books and saves the invoice record.
    """
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

    if ZOHO_ENABLED and req.vendor_zoho_id:
        try:
            zoho_line_items = [
                {
                    "item_id": li.zoho_item_id,
                    "name": li.zoho_item_name,
                    "quantity": li.qty,
                    "rate": li.rate,
                }
                for li in req.line_items
            ]
            result = create_bill(
                vendor_id=req.vendor_zoho_id,
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
    redirect_uri: str  # e.g. "http://localhost:8001/zoho/callback"


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
async def zoho_callback(code: str, redirect_uri: str = "http://localhost:8001/zoho/callback"):
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


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "zoho_enabled": ZOHO_ENABLED}
