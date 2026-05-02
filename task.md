# BillSync — Task Tracker

> **Stack:** FastAPI · MongoDB · React + Vite · Docker  
> **Source of truth for products/bills:** Zoho Books  
> **Constraint:** Human must confirm before any bill is created

---

## Legend
- ✅ Done  
- 🔄 In Progress  
- ⬜ Pending  
- 🐛 Bug / Known Issue

---

## ✅ Phase 1 — Backend Foundation
- [x] Dockerize FastAPI backend
- [x] Remove local MongoDB from docker-compose; use external MONGO_URI
- [x] `POST /upload-invoice/` — PDF upload + text extraction
- [x] Temp PDF storage in UPLOAD_DIR
- [x] Detect PDF type (text vs image)
- [x] Extract text with pdfplumber (primary) + PyMuPDF (fallback)
- [x] OCR fallback via PaddleOCR + pdf2image
- [x] `backend/db.py` — MongoDB collections + indexes
- [x] `backend/parser.py` — parse_invoice_lines, extract_invoice_metadata

## ✅ Phase 2 — Invoice Processing
- [x] Parse line items (index, product name, qty, rate, amount)
- [x] Handle multi-line names, noise tokens, malformed rows
- [x] `POST /process-invoice/` endpoint
- [x] Duplicate invoice guard (invoice_number check in MongoDB)
- [x] Numeric field validation

## ✅ Phase 3 — Product Mapping
- [x] `backend/matcher.py` — rapidfuzz fuzzy matching
- [x] DB lookup for existing mappings
- [x] Return top fuzzy candidates when no mapping found
- [x] `POST /mappings/` — save confirmed mapping
- [x] `GET /mappings/{vendor_product_name}` — lookup mapping

## ✅ Phase 4 — Zoho Integration
- [x] `backend/zoho.py` — OAuth token refresh
- [x] Fetch Zoho items → cache in `product_cache` collection
- [x] `POST /confirm-invoice/` → create Zoho purchase bill
- [x] Graceful degradation when Zoho credentials missing
- [x] `GET /zoho/sync-items/` — manual sync endpoint

## ✅ Phase 5 — Price & Status Detection
- [x] `backend/price_checker.py` — compare rate vs last stored price
- [x] Status enum: `normal` / `price_change` / `new_product`
- [x] `save_price_history()` called after bill confirmation
- [x] price_detail returned per line item

## ✅ Phase 6 — Auto-sync & Infrastructure
- [x] APScheduler weekly Zoho sync job
- [x] docker-compose.yml (backend + frontend services)
- [x] frontend/Dockerfile (multi-stage nginx build)
- [x] frontend/nginx.conf (API proxy + SPA fallback)
- [x] .env.example with all required vars
- [x] Structured logging throughout

## ✅ Phase 7 — Frontend v1 (Functional)
- [x] UploadPage — drag-and-drop PDF upload
- [x] Processing spinner
- [x] ReviewPage — item table with vendor name, Zoho mapping select, qty, rate, amount, status badge
- [x] Fuzzy candidate dropdown (HTML `<select>`)
- [x] Remove / restore line items
- [x] Sync Zoho Items button
- [x] Confirm & Create Bill button with toast feedback
- [x] Toast notification system

## ✅ Phase 9 — Adaptive Parser Fix
- [x] Numeric splitting for squashed PDF text
- [x] Heuristic (Qty × Rate ≈ Amount) validation

---

## ✅ Known Bugs — FIXED

### ✅ P0 (Critical — Blocking Zoho Integration)
- [x] **`vendor_zoho_id` always null** ✅ FIXED (Phase 11.4)
  - Added `VENDOR_ZOHO_ID = os.environ.get("VENDOR_ZOHO_ID")` to main.py
  - `confirm_invoice()` now uses `VENDOR_ZOHO_ID or req.vendor_zoho_id`
  - Added `GET /config/` endpoint to report `vendor_zoho_id_configured` status

- [x] **Filename collision** ✅ FIXED (Phase 11.5)
  - Implemented timestamp + UUID prefix: `{YYYYMMDD}_{HHMMSS}_{uuid8}_{filename}`
  - Prevents concurrent upload overwrites
  - Response includes `saved_filename` for tracking

### ✅ P1 (High — Parser Robustness)
- [x] **OCR line ordering** ✅ FIXED (Phase 11.8)
  - Updated `extract_text_ocr()` to sort blocks by Y-coordinate
  - Maintains top-to-bottom reading order from image PDFs
  - Fixes line item ordering issues

- [x] **Invoice number regex too narrow** ✅ FIXED (Phase 11.1)
  - Multi-pattern support added:
    - Format A: "Company Invoice No : TN2526058332"
    - Format B: "INV-1234"
    - Format C: "MM/2026/0087"
    - Format D: "Invoice #12345"
    - Format E: Freeform alphanumeric fallback
  - Debug logging for pattern matching
  - Warning when no pattern matches

---

## 🔄 Phase 10 — UI Redesign (Match BillSync-ui.html Reference)

The reference design (`BillSync-ui.html`) is significantly more polished than the current v1 frontend. Phase 10 is **substantially complete** with core components implemented.

### 10.1 Design System & Global Styles
- [x] CSS variable design system in `index.css`:
  - Primary: `--primary: #2563eb`, `--primary-ink: #1d4ed8`, `--primary-soft: #eff4ff` ✅
  - Status: `--ok: #059669` · `--warn: #b45309` · `--err: #b91c1c` (each with `-soft` and `-border` variants) ✅
  - Surfaces: `--bg` · `--surface` · `--surface-2` · `--border` · `--border-strong` ✅
  - Text: `--ink` · `--ink-2` · `--ink-3` ✅
  - Shadows: `--shadow-sm` · `--shadow-md` · `--shadow-lg` ✅
  - Fonts: Inter (UI, `--font-ui`) + JetBrains Mono (numbers, `--font-num`) ✅
  - `--row-h: 56px` ✅

### 10.2 Upload Screen
- [x] Centered card with drag-and-drop ✅
- [x] File-selected state: PDF icon + filename + file size ✅
- [x] "Process Invoice" button ✅
- [x] Disable button until file is selected
- [x] Hint text: "Milky Mist invoices only · Max 25 MB"

### 10.3 Processing Screen
- [x] Animated step-list with states:
  1. Reading PDF ✅
  2. Extracting line items ✅
  3. Matching to your products ✅
  4. Checking price history ✅
- [x] Step states: pending (dim circle) → active (spinning border, blue) → done (filled green ✓) ✅
- [x] Progress bar below step list ✅
- [x] Step transitions with 600ms delay ✅

### 10.4 Review Screen — Meta Card
- [x] 4-column grid card above the table:
  - Vendor (18px bold) | Invoice # | Invoice Date | Grand Total (22px bold, rightmost)
- [x] Labels: 12px uppercase letter-spaced, muted (`--ink-3`)
- [x] Card: `background: var(--surface)` · `border-radius: 12px` · `box-shadow: var(--shadow-sm)`

### 10.5 Review Screen — Table Toolbar
- [x] Title: "Line Items" + count ✅
- [x] Filter chips (pill toggles, multi-select) ✅
  - **All** (default active) ✅
  - **⚠ Price Changes (N)** ✅
  - **🔴 New Products (N)** ✅
- [x] Active chip styling ✅
- [ ] Search input with magnifier icon (240px): live filter by product name
- [ ] Chips + search work together (AND logic)

### 10.6 Review Screen — Items Table
Current implementation has core columns; Phase 11 adds disc/tax columns.

| Col      | Status | Notes |
|----------|--------|-------|
| #        | ✅ | Row index, muted |
| Product  | ✅ | Clickable cell → opens picker |
| Qty      | 🔄 | Right-aligned; editable via pencil icon (in progress) |
| Rate     | 🔄 | Right-aligned; editable (in progress) |
| Disc %   | ⬜ | Requires Phase 11 backend (disc_pct parsing) |
| Tax      | ⬜ | Requires Phase 11 backend (tax_pct parsing) |
| Total    | 🔄 | Calculated from qty × rate (in progress) |
| Status   | ✅ | Badge pill ✅ |
| Actions  | ⬜ | Edit (pencil) + Delete (trash) icons |

- [ ] Sticky header (verify sticky positioning)
- [ ] Row color coding:
  - `row-warn`: `--warn-bg-row` bg + 3px amber left border strip
  - `row-err`: `--err-bg-row` bg + 3px red left border strip
- [ ] Inline edit: click pencil → input replaces static text; blur/Enter saves; recalculates Total
- [ ] Discount pill: green rounded pill if disc > 0; transparent if 0

### 10.7 Product Picker (Custom Dropdown — Replaces `<select>`)
- [x] `ProductPicker.jsx` component created ✅
- [x] Floating panel (search input + scrollable list) ✅
- [x] Item name + SKU + score display ✅
- [x] Keyboard nav: ↑↓, Enter, Esc ✅
- [x] Empty state message ✅
- [ ] Keyboard navigation (↑↓) implementation (verify fullness)
- [ ] Picker calls `GET /zoho/items/?q=<search>` for real-time search (Phase 11.4)

### 10.8 Price History Tooltip
- [ ] Hover over Rate cell → tooltip appears (top-center, dark bg, arrow):
  - Previous rate (red if increased, green if decreased)
  - Current rate
  - Delta: `▲ +12.5%` or `▼ -3.2%`
  - Last seen date
- [ ] Only shown if `price_detail.previous_rate` exists in item data

### 10.9 Totals Card
- [ ] Right-aligned card below table (max-width 440px):
  - Subtotal
  - Discount total (green, shown as negative)
  - Tax total
  - Dashed divider
  - **Grand Total** (20–22px, bold 700)
- [ ] Values: right-aligned, `var(--font-num)`, `font-variant-numeric: tabular-nums`
- [ ] Data sourced from `/process-invoice/` `totals` object (Phase 11.2)

### 10.10 Fixed Action Bar (Bottom)
- [x] Bottom action bar with summary ✅
- [x] Summary: "N items · N price changes · N unmapped" ✅
- [x] "Confirm & Create Bill →" primary button ✅
- [x] Disable confirmation if unmapped > 0 ✅

### 10.11 PDF Preview Side Panel (Optional Enhancement)
- [ ] Toggle button: "Show PDF ▸" / "Hide PDF ◂"
- [ ] When open: 2-column grid layout (`1fr 380px`)
- [ ] Panel: sticky, scrollable, monospace font
- [ ] Panel header: "Original Invoice" label + close ✕

### 10.12 Done / Success Screen
- [ ] Centered card after bill creation:
  - Animated green circle ✓
  - "Bill Created!" heading
  - Details grid: Invoice # · Zoho Bill ID · Total Amount
  - "Open in Zoho Books →" link
  - "Process Another Invoice" button → resets to upload
- [ ] Auto-dismiss success toast (top-right, 3.5s)

---

## ✅ Phase 11 — Parser & Backend Enhancements (Product Mapping & Business Rules) — MOSTLY COMPLETE

### ✅ 11.1 Invoice Number Pattern Recognition — COMPLETE
- [x] Expand invoice number regex to handle multiple Milky Mist formats ✅
- [x] Log a warning if invoice number regex doesn't match any known pattern ✅
- [x] **Benefit**: Duplicate guard now catches re-uploads in different number format ✅

### ✅ 11.2 Discount & Tax Per Line Item — COMPLETE
- [x] Update `parse_invoice_lines()` to extract `disc_pct`, `tax_pct`, `tax_amount` ✅
- [x] Table extraction already returns these fields ✅
- [x] Line-based parser now includes tax_amount calculation ✅
- [x] **Benefit**: Enables Phase 10.6 table columns (Disc % | Tax) ✅

### ✅ 11.3 Invoice Totals Object — COMPLETE
- [x] Compute totals in `/process-invoice/` ✅
  ```json
  "totals": {
    "subtotal": 0.0,
    "discount_total": 0.0,
    "tax_total": 0.0,
    "grand_total": 0.0
  }
  ```
- [x] All values rounded to 2 decimals ✅
- [x] **Benefit**: Phase 10.9 Totals Card displays these values ✅

### ✅ 11.4 Server-Side VENDOR_ZOHO_ID — COMPLETE
- [x] Add `VENDOR_ZOHO_ID` to env handling ✅
- [x] Read in `main.py` and use in `confirm_invoice()` ✅
- [x] Add `GET /config/` endpoint returning `vendor_zoho_id_configured` ✅
- [x] **Benefit**: Fixes P0 bug (Zoho bill creation failures) ✅

### ✅ 11.5 Filename Collision Fix — COMPLETE
- [x] Prefix saved filename with `{timestamp}_{uuid8}_{original_name}` ✅
- [x] Update response to return `saved_filename` ✅
- [x] **Benefit**: Eliminates data loss from concurrent upload collisions ✅

### ✅ 11.6 Product Mapping Query Endpoint — COMPLETE
- [x] `GET /zoho/items/?q=<query>&limit=10` ✅
- [x] Search `product_cache` (name + SKU, case-insensitive) ✅
- [x] Return fuzzy match scores ✅
- [x] Sort by score descending ✅
- [x] **Used by**: Phase 10.7 ProductPicker real-time search ✅
- [x] **Benefit**: Live product lookup without manual sync ✅

### ⬜ 11.7 Invoice History & Re-processing Endpoint — NOT YET
- [ ] `GET /invoices/?page=1&limit=20`
- [ ] Allow re-upload of `pending_zoho` invoices
- [ ] **Used by**: Phase 12 History Page

### ✅ 11.8 OCR Y-Coordinate Sorting — COMPLETE
- [x] Sort OCR blocks by Y-coordinate in `extract_text_ocr()` ✅
- [x] Maintains reading order (top-to-bottom) ✅
- [x] **Benefit**: Fixes P1 bug (line ordering on image PDFs) ✅

### ⬜ 11.9 Price Change Status Enhancements — NOT YET
- [ ] Return detailed `price_detail` object with deltas & history
- [ ] **Used by**: Phase 10.8 Price History Tooltip

### ✅ 11.10 Business Rules Documentation — COMPLETE
- [x] **Invoice Processing Flow** documented ✅
- [x] **Product Mapping Rules** documented ✅
- [x] **Price Change Detection** logic documented ✅
- [x] **Zoho Integration Constraints** documented ✅

---

## ⬜ Phase 12 — Invoice History Page (Low Priority)
- [ ] `HistoryPage.jsx` — linked from topbar
- [ ] Table: Invoice # · Date · Status pill · Total · Bill ID · "View" link
- [ ] Status pills: confirmed (green) / pending_zoho (amber) / failed (red)
- [ ] "Re-process" button for pending_zoho invoices
- [ ] Pagination (page 1 of N)

---

## ⬜ Phase 13 — Testing & Hardening

### 13.1 Parser Tests
- [ ] `tests/test_parser.py` with real-text fixtures from `invoice-sample.pdf` OCR output
- [ ] Assert: item count, product names, qty, rate, amount
- [ ] Edge cases: multi-line names, squashed tokens, total-only rows, blank rows

### 13.2 API Contract Tests
- [ ] `tests/test_api.py` using FastAPI `TestClient`
- [ ] Full flow: upload → process → confirm (mock Zoho)
- [ ] Duplicate invoice rejection (409)
- [ ] Missing text payload (400)

### 13.3 Zoho Error Handling
- [ ] Auto-retry once on 401 (refresh token, then retry original request)
- [ ] On network timeout: save invoice as `pending_zoho`, return partial success response
- [ ] Surface Zoho validation error messages to the user (not just a generic "Zoho error")

### 13.4 Startup Health Checks
- [ ] Log structured warnings at startup for each missing env var
- [ ] `/health` endpoint returns: `{ mongo_connected, zoho_configured, vendor_id_set, scheduler_running }`

---

## 📋 Implementation Priority — UPDATED

**Status**: Phase 11 P0-P2 items **COMPLETE** ✅ · Ready for UI integration & remaining enhancements

| Priority | Task | Status | Phase |
|----------|------|--------|-------|
| 🔴 P0 | Fix `vendor_zoho_id` null bug | ✅ DONE | 11.4 |
| 🔴 P0 | Filename collision fix | ✅ DONE | 11.5 |
| 🟠 P1 | Fix OCR Y-coordinate sorting | ✅ DONE | 11.8 |
| 🟠 P1 | Expand invoice number regex | ✅ DONE | 11.1 |
| 🟡 P2 | Discount & tax per line item | ✅ DONE | 11.2 |
| 🟡 P2 | Invoice totals object | ✅ DONE | 11.3 |
| 🟡 P2 | Product search endpoint | ✅ DONE | 11.6 |
| 🟡 P2 | Complete UI phases 10.4–10.12 | 🔄 In Progress | 10 |
| 🟢 P3 | Price history enhancements | ⬜ Pending | 11.9 |
| 🟢 P3 | Invoice history endpoint | ⬜ Pending | 11.7 |
| 🔵 P4 | History page | ⬜ Pending | 12 |
| 🔵 P4 | Tests (parser, API, Zoho) | ⬜ Pending | 13 |

### What's Ready Now
- ✅ **All P0-P1 bug fixes** — Production-blocking issues resolved
- ✅ **All P2 business logic** — Backend enhancements complete
- ✅ **3 new API endpoints** — `/config/`, `/zoho/items/`, totals calculation
- ✅ **Parser enhancements** — Multi-format invoice numbers, tax/discount fields, Y-sorting
- ⏳ **Phase 10 UI** — 85% done; ready for final polish (meta card, totals card, success screen)

---

## 🗂 File Reference

```
billsync-app/
├── backend/
│   ├── main.py           # FastAPI app + all routes
│   ├── db.py             # MongoDB collection accessors + indexes
│   ├── parser.py         # PDF text → structured line items
│   ├── matcher.py        # rapidfuzz matching + mapping CRUD
│   ├── price_checker.py  # price history comparison + status enum
│   └── zoho.py           # Zoho Books API client (OAuth + items + bills)
├── frontend/src/
│   ├── App.jsx           # Screen router (upload → processing → review → done)
│   ├── index.css         # Global styles (⚠ full redesign in Phase 10.1)
│   ├── api.js            # API client functions
│   └── pages/
│       ├── UploadPage.jsx    # Upload + drag-drop
│       └── ReviewPage.jsx    # Review table + confirm
├── BillSync-ui.html      # ← Reference UI design (Claude artifact — do not modify)
├── invoice-sample.pdf    # ← Milky Mist sample invoice for parser testing
├── docker-compose.yml
└── .env.example
```
