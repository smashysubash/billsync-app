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

## 🐛 Known Bugs & Quick Fixes

- [ ] **`vendor_zoho_id` always null** — `confirm_invoice` sends `vendor_zoho_id: null`; Zoho bill creation silently skips. Fix: read `VENDOR_ZOHO_ID` from env in `main.py` and use it server-side.
- [ ] **Filename collision** — uploading two files with the same name overwrites the first file on disk. Prefix with `datetime.utcnow().strftime("%Y%m%d_%H%M%S_")`.
- [ ] **OCR line ordering** — PaddleOCR returns blocks out of reading order on some layouts; sort by Y-coordinate before passing to parser.
- [ ] **Invoice number regex too narrow** — only catches one format. Milky Mist uses several patterns (`INV-XXXX`, `MM/YYYY/NNNN`, etc.). Add multi-pattern fallback with a logging warning when none match.

---

## ⬜ Phase 10 — UI Redesign (Match BillSync-ui.html Reference)

The reference design (`BillSync-ui.html`) is significantly more polished than the current v1 frontend. This phase rebuilds the React UI to match it.

### 10.1 Design System & Global Styles
- [ ] Replace `index.css` with CSS variable design system:
  - Primary: `--primary: #2563eb`, `--primary-ink: #1d4ed8`, `--primary-soft: #eff4ff`
  - Status: `--ok: #059669` · `--warn: #b45309` · `--err: #b91c1c` (each with `-soft` and `-border` variants)
  - Surfaces: `--bg` · `--surface` · `--surface-2` · `--border` · `--border-strong`
  - Text: `--ink` · `--ink-2` · `--ink-3`
  - Shadows: `--shadow-sm` · `--shadow-md` · `--shadow-lg`
  - Fonts: Inter (UI, `--font-ui`) + JetBrains Mono (numbers, `--font-num`)
  - `--row-h: 56px`
- [ ] Dark mode toggle: `[data-theme="dark"]` on `<body>`, button in topbar
- [ ] Density toggle: comfortable (default, 56px rows) ↔ compact (44px rows)

### 10.2 Upload Screen
- [ ] Centered card (560px max, `border-radius: 16px`, `box-shadow: var(--shadow-md)`)
- [ ] Dropzone: `border: 2px dashed` → solid blue border when dragging or file selected
- [ ] File-selected state: PDF icon + filename + file size + remove ✕ button (side-by-side layout)
- [ ] Disable "Process Invoice" button until file is selected
- [ ] Hint text: "Milky Mist invoices only · Max 25 MB"

### 10.3 Processing Screen
- [ ] Replace plain spinner with step-list:
  1. Uploading PDF
  2. Extracting text
  3. Parsing line items
  4. Matching products
- [ ] Step states: pending (dim circle) → active (spinning border, blue) → done (filled green ✓)
- [ ] Thin progress bar (`height: 4px`) below step list
- [ ] Animate step transitions with 600ms delay each (frontend simulates progress; final step waits for API response)

### 10.4 Review Screen — Meta Card
- [ ] 4-column grid card above the table:
  - Vendor (18px bold) | Invoice # | Invoice Date | Grand Total (22px bold, rightmost)
- [ ] Labels: 12px uppercase letter-spaced, muted (`--ink-3`)
- [ ] Card: `background: var(--surface)` · `border-radius: 12px` · `box-shadow: var(--shadow-sm)`

### 10.5 Review Screen — Table Toolbar
- [ ] Title: "Line Items" + count in muted parenthesis
- [ ] Filter chips (pill toggles, multi-select):
  - **All** (default active)
  - **⚠ Price Changes (N)** — amber dot
  - **🔴 New Products (N)** — red dot
- [ ] Active chip: `background: var(--ink); color: #fff`
- [ ] Search input (240px, magnifier icon): live filter by product name
- [ ] Chips + search work together (AND logic)

### 10.6 Review Screen — Items Table
New columns (backend must return disc/tax — see Phase 11):

| Col      | Width | Notes |
|----------|-------|-------|
| #        | 40px  | Row index, muted |
| Product  | 240px+| Clickable cell → opens picker |
| Qty      | 90px  | Right-aligned; editable via pencil icon |
| Rate     | 120px | Right-aligned; editable; hover tooltip shows history |
| Disc %   | 88px  | Green pill if > 0; muted placeholder if 0 |
| Tax      | 80px  | "12% GST" style, muted |
| Total    | 120px | Bold, right-aligned |
| Status   | 150px | Badge pill |
| Actions  | 84px  | Edit (pencil) + Delete (trash) icons |

- [ ] Sticky header (`position: sticky; top: 0; z-index: 2; background: var(--surface-2)`)
- [ ] Scrollable body (`max-height: 62vh; overflow-y: auto`)
- [ ] Row color coding:
  - `row-warn`: `--warn-bg-row` bg + 3px amber left border strip
  - `row-err`: `--err-bg-row` bg + 3px red left border strip
  - `row-editing`: `#f0f6ff` bg + 3px blue left border strip
- [ ] Inline edit: click pencil → input replaces static text; blur/Enter saves; recalculates Total
- [ ] Discount pill: green rounded pill (`--ok-soft` bg) if disc > 0; transparent if 0

### 10.7 Product Picker (Custom Dropdown — Replaces `<select>`)
- [ ] Create `ProductPicker.jsx` component
- [ ] Click product name → floating panel (360px wide, `border-radius: 10px`, `box-shadow: var(--shadow-lg)`, `z-index: 30`)
- [ ] Panel contents:
  - Search input (autofocused, full-width, no border except bottom)
  - Scrollable list (max 280px): item name + SKU (12px monospace, muted)
  - Hover/active highlight: `var(--primary-soft)`
  - Empty state: "No matches — try Sync Zoho Items"
  - Footer: keyboard shortcut hints (`↑↓` navigate · `Enter` select · `Esc` close)
- [ ] Keyboard nav: ↑↓ move active item, Enter selects, Esc closes
- [ ] "Needs mapping" state: red border on product cell, red text, "Select product →" chevron
- [ ] After selection: product name + muted brand text on second line
- [ ] Picker calls `GET /zoho/items/?q=<search>` for real-time search (Phase 11.4)

### 10.8 Price History Tooltip
- [ ] Hover over Rate cell → tooltip appears (top-center, dark bg, arrow):
  - Previous rate (red if increased, green if decreased)
  - Current rate
  - Delta: `▲ +12.5%` or `▼ -3.2%`
  - Last seen date
- [ ] Transition: `opacity 0.15s`
- [ ] Only shown if `price_detail.previous_rate` exists in item data

### 10.9 Totals Card
- [ ] Right-aligned card below table (max-width 440px, `margin-left: auto`):
  - Subtotal
  - Discount total (green, shown as negative)
  - Tax total
  - Dashed divider (`border-top: 1px dashed var(--border-strong)`)
  - **Grand Total** (20–22px, bold 700)
  - Small "incl. GST" note below grand total
- [ ] Values: right-aligned, `var(--font-num)`, `font-variant-numeric: tabular-nums`
- [ ] Data sourced from `/process-invoice/` `totals` object (Phase 11.2)

### 10.10 Fixed Action Bar (Bottom)
- [ ] `position: fixed; bottom: 0; left: 0; right: 0` bar
- [ ] Left: summary — "12 items · 2 price changes · 1 unmapped"
- [ ] Right: "Confirm & Create Bill →" primary button (lg size)
- [ ] If unmapped > 0: red inline blocker chip ("1 product needs mapping"); Confirm button disabled
- [ ] Add `padding-bottom: 100px` to review content to prevent overlap

### 10.11 PDF Preview Side Panel
- [ ] Toggle button in toolbar: "Show PDF ▸" / "Hide PDF ◂"
- [ ] When open: review layout changes to 2-column grid (`1fr 380px`)
- [ ] Panel: sticky (`top: 76px`), scrollable, monospace font, shows parsed invoice table
- [ ] Panel header: "Original Invoice" label + close ✕ button

### 10.12 Done / Success Screen
- [ ] Centered card after bill creation (min-width 520px):
  - Animated green circle ✓ (CSS `scale(0) → scale(1)` cubic-bezier)
  - "Bill Created!" heading (22px, semibold)
  - Details grid: Invoice # · Zoho Bill ID · Total Amount · Date
  - "Open in Zoho Books →" link (opens new tab to Zoho bill)
  - "Process Another Invoice" secondary button → resets to upload
- [ ] Auto-dismiss success toast (top-right, 3.5s) showing bill number
- [ ] Do NOT auto-redirect — let user choose when to go back

---

## ⬜ Phase 11 — Parser & Backend Enhancements

### 11.1 Discount & Tax Per Line Item
- [ ] Update `parse_invoice_lines()` to extract `disc_pct` and `tax_pct` from each row
- [ ] Compute `tax_amount = rate * qty * tax_pct / 100`
- [ ] Add `disc_pct`, `tax_pct`, `tax_amount` fields to each line item in the response

### 11.2 Invoice Totals Object
- [ ] After parsing all line items, compute and return:
  ```json
  "totals": {
    "subtotal": 0.0,
    "discount_total": 0.0,
    "tax_total": 0.0,
    "grand_total": 0.0
  }
  ```
- [ ] Frontend Totals Card (Phase 10.9) reads from this object

### 11.3 Server-Side VENDOR_ZOHO_ID
- [ ] Add `VENDOR_ZOHO_ID` to `.env.example` with explanation comment
- [ ] Read in `main.py`: `VENDOR_ZOHO_ID = os.environ.get("VENDOR_ZOHO_ID")`
- [ ] Use it in `confirm_invoice()` — remove dependency on frontend passing it
- [ ] Add `GET /config/` → `{ "vendor_zoho_id_configured": bool, "zoho_enabled": bool }`
- [ ] Frontend shows amber warning banner on review screen if `vendor_zoho_id_configured` is false

### 11.4 Zoho Items Search Endpoint
- [ ] `GET /zoho/items/?q=<query>&limit=10`
- [ ] Search `product_cache` in MongoDB (case-insensitive regex or text index)
- [ ] Returns: `[{ zoho_item_id, name, sku, rate }]`
- [ ] Used by ProductPicker for real-time search without re-syncing

### 11.5 Filename Collision Fix
- [ ] In `/upload-invoice/`: prefix saved filename with `datetime.utcnow().strftime("%Y%m%d_%H%M%S_")` + UUID4 first 8 chars

### 11.6 Invoice History Endpoint
- [ ] `GET /invoices/?page=1&limit=20`
- [ ] Returns: `[{ invoice_number, vendor, date, status, zoho_bill_id, grand_total, created_at }]`
- [ ] Allow re-upload of `pending_zoho` invoices (bypass duplicate guard for that status)

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

## 📋 Recommended Implementation Order

| Priority | Task | Reason |
|----------|------|--------|
| 🔴 P0 | Fix `vendor_zoho_id` null bug (Phase 11.3) | Zoho bills silently fail today |
| 🔴 P0 | Filename collision fix (Phase 11.5) | Data integrity |
| 🟠 P1 | Disc/tax/totals parsing (Phase 11.1–11.2) | Table has these columns; must work before redesign |
| 🟠 P1 | Zoho items search endpoint (Phase 11.4) | Required by new product picker |
| 🟡 P2 | Design system + upload + processing screens (Phase 10.1–10.3) | Foundation for rest of redesign |
| 🟡 P2 | Meta card + table toolbar + items table (Phase 10.4–10.6) | Core review screen |
| 🟡 P2 | Product picker component (Phase 10.7) | Replaces broken `<select>` UX |
| 🟡 P2 | Tooltips + totals card + action bar + done screen (Phase 10.8–10.12) | Complete the polish |
| 🟢 P3 | Startup health checks (Phase 13.4) | Ops visibility |
| 🟢 P3 | Tests (Phase 13.1–13.2) | Stability |
| ⚫ P4 | History page (Phase 12) | Nice-to-have |

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
