"""
parser.py — BillSync invoice parser (Milky Mist format).

Parsing Strategy
================
PRIMARY  — pdfplumber table extraction (page.extract_tables()).
  Works when pdfplumber can detect the ruling lines / column spacing.
  Produces perfectly-separated cells, so no heuristics are needed.

  Column layout expected (Milky Mist purchase invoice):
    0: # (row index)      1: ITEM name        2: BRAND
    3: PCS/BOX (qty/box)  4: BOX/CRATE        5: PCS PRICE (unit rate)
    6: BOX PRICE          7: CRATE PRICE      8: INVOICE QTY
    9: REC QTY           10: DISC.           11: CGST
   12: SGST              13: TOTAL (amount)

  qty  = INVOICE QTY  (col 8)  — how many pieces were actually invoiced
  rate = PCS PRICE    (col 5)  — per-piece price
  amt  = TOTAL        (col 13) — line total incl. GST

FALLBACK — line-based numeric-triplet heuristic.
  Used when table extraction returns nothing (e.g. image-rendered PDFs that
  went through OCR, or future vendors with different table borders).
  Handles squashed numeric tokens (e.g. "58.748811.00") by splitting them.
"""

import re
import logging
from typing import Optional

import pdfplumber

logger = logging.getLogger(__name__)

# ── Shared constants ──────────────────────────────────────────────────────────

# Tokens stripped only from line-based (flattened) product names where brand
# fragments leak into the name column.  Units (GM, ML, LTR …) are intentionally
# NOT included so table-extracted names like "UHT CREAM - 1 LTR (MMD)" stay intact.
_LINE_NOISE_TOKENS = {
    "milky", "mist", "mmd",
    "nos", "nos.",
    "pcs", "pcs.",
    "box", "ctn", "carton", "pack", "packet",
}

# Tokens stripped from the *brand* column only (table mode uses a dedicated cell)
_BRAND_TOKENS = {"milky", "mist", "milkymist"}

_TOTAL_KEYWORDS = re.compile(
    r"^\s*(total|sub.?total|grand.?total|amount|vat|gst|sgst|cgst|igst|tax)\b",
    re.IGNORECASE,
)

_ITEM_ROW_RE = re.compile(r"^\d{1,3}\s+")
_NUMBER_RE = re.compile(r"^\d[\d,]*(\.\d+)?$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_float(token: str) -> Optional[float]:
    """Convert a token like '1,234.56' or '150 Pcs' to float, or None."""
    if not token:
        return None
    # Strip trailing unit labels like " Pcs", " pcs", " KG", etc.
    token = re.sub(r"\s*(pcs|pcs\.|nos|kg|ltr|ml|gm|g)\s*$", "", token.strip(), flags=re.IGNORECASE)
    try:
        clean = re.sub(r"[^\d.\-]", "", token.replace(",", ""))
        if clean in ("", ".", "-"):
            return None
        return float(clean)
    except ValueError:
        return None


def _clean_name_table(name: str) -> str:
    """Clean a table-extracted product name: strip only brand tokens."""
    tokens = name.split()
    filtered = [t for t in tokens if t.lower() not in _BRAND_TOKENS and t]
    return " ".join(filtered).strip()


def _clean_name_line(tokens: list[str]) -> str:
    """Clean a line-parsed name token list: strip brand + layout noise."""
    filtered = [t for t in tokens if t.lower() not in _LINE_NOISE_TOKENS and t]
    return " ".join(filtered).strip()


# ── PRIMARY: pdfplumber table extraction ─────────────────────────────────────

# Expected column indices in the Milky Mist table header
_COL_INDEX   = 0
_COL_ITEM    = 1
_COL_RATE    = 5   # PCS PRICE
_COL_INV_QTY = 8   # INVOICE QTY
_COL_DISC    = 10  # DISC.
_COL_CGST    = 11  # CGST
_COL_SGST    = 12  # SGST
_COL_TOTAL   = 13  # TOTAL

_HEADER_KEYWORDS = {"item", "brand", "price", "qty", "total", "disc", "cgst", "sgst"}


def _looks_like_header(row: list) -> bool:
    """Return True if a table row looks like a column-header row."""
    texts = [str(c or "").lower().strip() for c in row]
    matches = sum(1 for t in texts if any(kw in t for kw in _HEADER_KEYWORDS))
    return matches >= 3


def _pct(raw: str) -> float:
    """
    Parse a percentage string like '2.50%', '6.67%', or '0%' into a float
    (e.g. 2.5, 6.67, 0.0).  Returns 0.0 on failure.
    """
    try:
        return float(re.sub(r"[^\d.]", "", raw.strip()))
    except (ValueError, AttributeError):
        return 0.0


def _validate_amount(
    qty: float,
    rate: float,
    disc_pct: float,
    cgst_pct: float,
    sgst_pct: float,
    parsed_amt: float,
    idx: int,
    name: str,
) -> tuple[float, bool]:
    """
    Compute expected line total and compare with the parsed amount.

    Formula:
        base          = qty × rate
        after_disc    = base × (1 − disc_pct / 100)
        expected_amt  = after_disc × (1 + (cgst_pct + sgst_pct) / 100)

    Returns (expected_amt, amount_ok).
    amount_ok is False when the absolute deviation exceeds max(0.50, 0.5% of expected).
    """
    base       = qty * rate
    after_disc = base * (1 - disc_pct / 100)
    expected   = after_disc * (1 + (cgst_pct + sgst_pct) / 100)
    tolerance  = max(0.50, expected * 0.005)   # 0.5 % or ₹0.50, whichever is larger
    ok         = abs(expected - parsed_amt) <= tolerance

    if not ok:
        logger.warning(
            "Row #%d %-35s  amount MISMATCH: parsed=%.2f  expected=%.2f "
            "(qty=%.2f × rate=%.2f × (1−%.2f%%) × (1+%.2f%%+%.2f%%))",
            idx, name, parsed_amt, expected,
            qty, rate, disc_pct, cgst_pct, sgst_pct,
        )
    return round(expected, 2), ok


def _parse_table_row(row: list) -> Optional[dict]:
    """
    Convert one data row from pdfplumber into a structured item dict.
    Returns None if the row is a header, total, or otherwise unparseable.
    """
    if len(row) < 14:
        return None

    idx_raw  = str(row[_COL_INDEX]   or "").strip()
    name_raw = str(row[_COL_ITEM]    or "").strip()
    rate_raw = str(row[_COL_RATE]    or "").strip()
    qty_raw  = str(row[_COL_INV_QTY] or "").strip()
    disc_raw = str(row[_COL_DISC]    or "").strip()
    cgst_raw = str(row[_COL_CGST]    or "").strip()
    sgst_raw = str(row[_COL_SGST]    or "").strip()
    amt_raw  = str(row[_COL_TOTAL]   or "").strip()

    # Skip header row and total row
    if not idx_raw or not idx_raw[0].isdigit():
        return None
    if _looks_like_header(row):
        return None

    try:
        idx = int(idx_raw)
    except ValueError:
        return None

    if not name_raw:
        return None

    qty  = _to_float(qty_raw)
    rate = _to_float(rate_raw)
    amt  = _to_float(amt_raw)

    if qty is None or rate is None or amt is None:
        logger.warning("Table row #%d — could not parse numeric fields: qty=%r rate=%r amt=%r",
                       idx, qty_raw, rate_raw, amt_raw)
        return None

    disc_pct = _pct(disc_raw)
    cgst_pct = _pct(cgst_raw)
    sgst_pct = _pct(sgst_raw)

    product_name = _clean_name_table(name_raw)
    if not product_name:
        return None

    expected_amt, amount_ok = _validate_amount(
        qty, rate, disc_pct, cgst_pct, sgst_pct, amt, idx, product_name
    )

    return {
        "index":         idx,
        "product_name":  product_name,
        "qty":           qty,
        "rate":          rate,
        "disc_pct":      disc_pct,
        "cgst_pct":      cgst_pct,
        "sgst_pct":      sgst_pct,
        "amount":        amt,
        "expected_amount": expected_amt,
        "amount_ok":     amount_ok,
    }


def _parse_via_table(file_path: str) -> list[dict]:
    """
    Open the PDF with pdfplumber and attempt table-based extraction.
    Returns a list of item dicts (may be empty if no suitable table found).
    """
    items: list[dict] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    # Only process the table that has enough columns (item table)
                    if len(table[0]) < 10:
                        continue
                    for row in table:
                        parsed = _parse_table_row(row)
                        if parsed:
                            items.append(parsed)
    except Exception as e:
        logger.warning("pdfplumber table extraction failed: %s", e)

    logger.info("Table extraction produced %d items", len(items))
    return items


# ── FALLBACK: line-based heuristic parsing ────────────────────────────────────

def _try_split_squashed(token: str) -> list[float]:
    """
    Handle squashed numeric tokens like '58.748811.00'.
    Returns a list of floats found within the string.
    """
    parts = re.findall(r"\d+\.\d{2}|\d+", token)
    return [f for p in parts if (f := _to_float(p)) is not None]


def _find_best_triplet(nums: list[float]) -> Optional[tuple[float, float, float]]:
    """
    Search for (Qty, Rate, Amount) such that Qty * Rate ≈ Amount.
    Returns the highest-scoring triplet or None.
    """
    if len(nums) < 3:
        return None

    candidates = []
    for i, qty in enumerate(nums):
        if qty <= 0:
            continue
        for j, rate in enumerate(nums):
            if i == j or rate <= 0:
                continue
            for k, amt in enumerate(nums):
                if k in (i, j) or amt <= 0:
                    continue
                if abs(qty * rate - amt) < max(0.5, amt * 0.01):
                    score = 0
                    if k > i and k > j:          score += 20   # amt last
                    if i < j:                    score += 10   # qty before rate
                    if rate > 1.0 and amt > 1.0: score += 10
                    if qty == int(qty):           score += 5    # whole-number qty
                    if amt >= rate and amt >= qty: score += 10
                    if i > 0 and j > 0:          score += 5    # skip leading index
                    if j + 1 == k:               score += 25   # rate adjacent to amt
                    score += (k / len(nums)) * 5               # amt towards end
                    candidates.append((score, (qty, rate, amt)))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# Regex: split a flattened line at item-index boundaries
# Matches a digit boundary immediately before 1-3 digits followed by an uppercase letter
_FLAT_ITEM_SPLIT_RE = re.compile(r"(?<=\d)(?=\s\d{1,3}[A-Z])")


def _pre_split_lines(raw_lines: list[str]) -> list[str]:
    """
    If the PDF collapsed all rows onto long lines, split them back at
    item-index boundaries (e.g. "27549.00 11PANEER" → two lines).
    """
    out = []
    for line in raw_lines:
        if len(line) > 80 and re.search(r"\s\d{1,3}[A-Z]", line):
            parts = _FLAT_ITEM_SPLIT_RE.split(line)
            out.extend(p.strip() for p in parts if p.strip())
        else:
            out.append(line)
    return out


def _parse_via_lines(text: str) -> list[dict]:
    """
    Line-based fallback parser.  Works on raw extracted text when
    pdfplumber cannot find a structured table.
    """
    raw_lines = text.splitlines()
    lines = _pre_split_lines(raw_lines)

    items: list[dict] = []
    current_item: Optional[dict] = None
    in_item_section = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if _TOTAL_KEYWORDS.match(line):
            current_item = None
            in_item_section = False
            continue

        if _ITEM_ROW_RE.match(line):
            in_item_section = True
            tokens = line.split()

            all_nums: list[float] = []
            for t in tokens:
                v = _to_float(t)
                if v is not None:
                    all_nums.append(v)
                else:
                    all_nums.extend(_try_split_squashed(t))

            triplet = _find_best_triplet(all_nums[1:])  # skip leading row-index
            if not triplet:
                logger.warning("Could not find triplet in row: %r", line)
                current_item = None
                continue

            qty, rate, amount = triplet
            try:
                idx = int(tokens[0])
            except ValueError:
                idx = 0

            name_tokens = []
            for t in tokens[1:]:
                if _to_float(t) is not None or _try_split_squashed(t):
                    break
                name_tokens.append(t)

            product_name = _clean_name_line(name_tokens)
            current_item = {
                "index": idx,
                "product_name": product_name,
                "qty": qty,
                "rate": rate,
                "amount": amount,
            }
            items.append(current_item)

        elif in_item_section and current_item is not None:
            # Continuation of a multi-line product name
            if not _NUMBER_RE.match(line) and not _ITEM_ROW_RE.match(line):
                current_item["product_name"] = (
                    current_item["product_name"] + " " + line
                ).strip()

    logger.info("Line-based extraction produced %d items", len(items))
    return items


# ── Public API ────────────────────────────────────────────────────────────────

def parse_invoice_lines(text: str, file_path: Optional[str] = None) -> list[dict]:
    """
    Parse a Milky Mist purchase invoice into structured line items.

    Tries pdfplumber table extraction first (requires file_path).
    Falls back to line-based heuristic parsing of the raw ``text``.

    Args:
        text:      Raw text string extracted from the PDF.
        file_path: Path to the original PDF file (enables table extraction).

    Returns:
        List of dicts with keys: index, product_name, qty, rate, amount.
    """
    # ── Primary: table extraction ──────────────────────────────────────────
    if file_path:
        items = _parse_via_table(file_path)
        if items:
            logger.info("Using table-extracted items (%d)", len(items))
            return items
        logger.info("Table extraction found no items — falling back to line parser")

    # ── Fallback: line-based heuristic ─────────────────────────────────────
    items = _parse_via_lines(text)
    return items


def extract_invoice_metadata(text: str) -> dict:
    """
    Best-effort extraction of invoice header fields:
      invoice_number, invoice_date, vendor
    """
    meta = {"invoice_number": None, "invoice_date": None, "vendor": "Milky Mist"}

    for line in text.splitlines():
        line = line.strip()

        # Invoice number: "Company Invoice No : TN2526058332(13-Feb-2026)"
        m = re.search(
            r"company\s+invoice\s+no\s*[:\.]?\s*([A-Z0-9]+)",
            line,
            re.IGNORECASE,
        )
        if m and not meta["invoice_number"]:
            meta["invoice_number"] = m.group(1).strip()

        # Fallback: generic invoice/bill number patterns
        if not meta["invoice_number"]:
            m = re.search(
                r"(?:invoice|bill)\s*(?:no|number|#)[:\.]?\s*([A-Z0-9/-]+)",
                line,
                re.IGNORECASE,
            )
            if m:
                meta["invoice_number"] = m.group(1).strip()

        # Date: "Purchase Invoice Date : 13-Feb-2026 12:00 PM"
        m = re.search(
            r"purchase\s+invoice\s+date\s*[:\.]?\s*(\d{1,2}-\w{3}-\d{4})",
            line,
            re.IGNORECASE,
        )
        if m and not meta["invoice_date"]:
            meta["invoice_date"] = m.group(1).strip()

        # Fallback: generic date patterns
        if not meta["invoice_date"]:
            m = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", line)
            if m:
                meta["invoice_date"] = m.group(1)

    return meta
