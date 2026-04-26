"""
parser.py — Milky Mist invoice text parser.

Strategy:
  1. Pre-process: split flat single-line text back into per-item rows by
     detecting patterns like "27549.00 11PANEER" where a new item index
     runs directly into the next product name.
  2. For each row that starts with a numeric index, extract all numeric
     tokens and use a math-based heuristic to find (Qty, Rate, Amount).
  3. Everything between the index and the first numeric token is the name.
  4. Multi-line names (from normal PDFs) are appended to the preceding item.
  5. Malformed rows are skipped safely.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Tokens to strip from product names (units, brand fragments, etc.)
NOISE_TOKENS = {
    "milky", "mist", "nos", "pcs", "kg", "ltr", "pkt", "gm", "ml",
    "box", "ctn", "carton", "pack", "packet", "nos.", "pcs.", "kg.",
    "mmd",
}

# A row that starts an item (leading integer index)
_ITEM_ROW_RE = re.compile(r"^\d{1,3}\s+")

# Patterns that signal end of item section
_TOTAL_KEYWORDS = re.compile(
    r"^\s*(total|sub.?total|grand.?total|amount|vat|gst|sgst|cgst|igst|tax)\b",
    re.IGNORECASE,
)

# Pattern that looks like a pure-number token (qty / rate / amount)
_NUMBER_RE = re.compile(r"^\d[\d,]*(\.\d+)?$")

# Pattern to detect a new item boundary in a flattened line:
#   <amount-like-number> <1-3 digit index><UPPERCASE letter>
# e.g. "27549.00 11PANEER" or "4892.40 12SET"
_FLAT_ITEM_SPLIT_RE = re.compile(r"(?<=\S)\s+(?=\d{1,3}[A-Z])")


def _to_float(token: str) -> Optional[float]:
    """Convert a token like '1,234.56' to float, or None on failure."""
    if not token:
        return None
    try:
        clean = re.sub(r"[^\d\.\-]", "", token.replace(",", ""))
        if clean in ("", ".", "-"):
            return None
        return float(clean)
    except ValueError:
        return None


def _clean_name(tokens: list[str]) -> str:
    """Remove noise tokens and collapse whitespace."""
    filtered = [t for t in tokens if t.lower() not in NOISE_TOKENS and t]
    return " ".join(filtered).strip()


def _try_split_squashed(token: str) -> list[float]:
    """
    Handle squashed numeric tokens like '58.748811.00'.
    Returns a list of floats found within the string.
    """
    parts = re.findall(r"\d+\.\d{2}", token)
    floats = []
    for p in parts:
        v = _to_float(p)
        if v is not None:
            floats.append(v)
    return floats


def _find_best_triplet(nums: list[float]) -> Optional[tuple[float, float, float]]:
    """
    Search for a (Qty, Rate, Amount) triplet such that Qty * Rate ≈ Amount.
    Returns (Qty, Rate, Amount) or None.
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
                if k == i or k == j or amt <= 0:
                    continue

                if abs(qty * rate - amt) < max(0.5, amt * 0.01):
                    score = 0

                    # Amount usually appears after Qty and Rate
                    if k > i and k > j:
                        score += 20

                    # Quantity usually appears BEFORE Rate
                    if i < j:
                        score += 10

                    # Rate and Amount are usually larger than 1.0
                    if rate > 1.0 and amt > 1.0:
                        score += 10

                    # Quantity is very often a whole number
                    if qty == int(qty):
                        score += 5

                    # Amount is usually larger than Qty and Rate
                    if amt >= rate and amt >= qty:
                        score += 10

                    # Avoid indices at the very start (often noise/index)
                    if i > 0 and j > 0:
                        score += 5

                    # ADJACENCY — Rate and Amount are almost always side-by-side
                    if j + 1 == k:
                        score += 25

                    # Tie-breaker: favour Amount closer to end
                    score += (k / len(nums)) * 5

                    candidates.append((score, (qty, rate, amt)))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _pre_split_lines(raw_lines: list[str]) -> list[str]:
    """
    If the PDF has collapsed all item rows onto one or a few long lines,
    split them back at item-index boundaries.

    Detects the pattern: whitespace + 1-3 digit number immediately followed
    by an uppercase letter (e.g. "27549.00 11PANEER").
    """
    out = []
    for line in raw_lines:
        # Only try to split long lines (> ~80 chars) that look like
        # they contain multiple item indices
        if len(line) > 80 and re.search(r"\s\d{1,3}[A-Z]", line):
            parts = _FLAT_ITEM_SPLIT_RE.split(line)
            out.extend(p.strip() for p in parts if p.strip())
        else:
            out.append(line)
    return out


def parse_invoice_lines(text: str) -> list[dict]:
    """
    Adaptive parsing of raw invoice text into structured line items.
    Handles both normally-structured PDFs and flattened single-line extractions.
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

        # Detect totals section → stop processing items
        if _TOTAL_KEYWORDS.match(line):
            current_item = None
            in_item_section = False
            continue

        if _ITEM_ROW_RE.match(line):
            in_item_section = True
            tokens = line.split()

            # Gather all numeric values (including squashed pairs)
            all_nums: list[float] = []
            for t in tokens:
                v = _to_float(t)
                if v is not None:
                    all_nums.append(v)
                else:
                    all_nums.extend(_try_split_squashed(t))

            # Skip the first number (row index) when looking for the triplet
            triplet = _find_best_triplet(all_nums[1:])

            if not triplet:
                logger.warning(
                    "Could not find (Qty, Rate, Amount) triplet in row: %r", line
                )
                current_item = None
                continue

            qty, rate, amount = triplet

            try:
                idx = int(tokens[0])
            except ValueError:
                idx = 0

            # Name tokens: everything between the index and the first
            # token that resolves to a number (or squashed numbers)
            name_tokens = []
            for t in tokens[1:]:
                if _to_float(t) is not None or _try_split_squashed(t):
                    break
                name_tokens.append(t)

            product_name = _clean_name(name_tokens)

            current_item = {
                "index": idx,
                "product_name": product_name,
                "qty": qty,
                "rate": rate,
                "amount": amount,
            }
            items.append(current_item)

        elif in_item_section and current_item is not None:
            # Continuation of a multi-line product name (normal PDFs)
            if not _NUMBER_RE.match(line) and not _ITEM_ROW_RE.match(line):
                current_item["product_name"] = (
                    current_item["product_name"] + " " + line
                ).strip()

    logger.info("Parsed %d line items", len(items))
    return items


def extract_invoice_metadata(text: str) -> dict:
    """
    Best-effort extraction of invoice header fields:
      invoice_number, invoice_date, vendor
    """
    meta = {"invoice_number": None, "invoice_date": None, "vendor": "Milky Mist"}

    for line in text.splitlines():
        line = line.strip()
        # Invoice number patterns: "Invoice No: 12345", "Bill No. ABC123"
        m = re.search(
            r"(?:invoice|bill)\s*(?:no|number|#)[:\.]?\s*([A-Z0-9/-]+)",
            line,
            re.IGNORECASE,
        )
        if m and not meta["invoice_number"]:
            meta["invoice_number"] = m.group(1).strip()

        # Date patterns: "Date: 01/04/2026" or "15-03-2026"
        m = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", line)
        if m and not meta["invoice_date"]:
            meta["invoice_date"] = m.group(1)

    return meta
