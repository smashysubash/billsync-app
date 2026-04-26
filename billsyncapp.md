You are a senior software engineer tasked with building a **single-tenant invoice automation system** that converts vendor PDF invoices into purchase bills in Zoho Books. The system must be reliable, simple, and production-ready for a low-volume distributor workflow.

---

# 🎯 Objective

Build a web application that:

1. Accepts PDF invoices from a specific vendor (Milky Mist).
2. Extracts structured data (items, qty, rate, tax, etc.).
3. Matches vendor product names to Zoho Books items.
4. Highlights price/MRP changes and new products.
5. Allows user confirmation via a simple UI.
6. Creates a purchase bill in Zoho Books via API.
7. Maintains a mapping database to avoid repeated matching.

---

# ⚠️ Constraints (DO NOT VIOLATE)

* Single company, single vendor (Milky Mist only).
* Low volume (1–3 invoices/day).
* Always require **human confirmation before creating bill**.
* No microservices. Use a **single backend service**.
* Prefer **deterministic parsing over AI**.
* Use AI/fuzzy matching only as fallback.
* MongoDB acts as **cache + memory**, NOT source of truth.
* Zoho Books is the **source of truth**.

---

# 🏗️ Architecture

Frontend:

* Simple web UI (React or minimal JS)
* Focus on clarity for non-technical users

Backend:

* Python (FastAPI preferred)
* Modular but in a single service

Database:

* MongoDB Atlas (free tier)

External:

* Zoho Books API (for items + bill creation)

---

# 📦 Core Components

## 1. Invoice Input

* Upload PDF
* Store temporarily (local or memory)

---

## 2. PDF Processing Pipeline

### Step 1 — Detect PDF type

* If text-based → use parser
* If no text → fallback to OCR

### Step 2 — Text Extraction

* Use `pdfplumber` as primary
* Fallback: PyMuPDF

### Step 3 — OCR (only if needed)

* Use PaddleOCR
* Convert PDF to image using pdf2image

---

## 3. Table Parsing Engine (Critical)

Implement a **robust parser**:

* Extract full text → split into lines
* Identify item section between header and total
* Detect rows using pattern:

  * starts with index number
* Tokenize line
* Extract from right:

  * amount → rate → qty
* Remaining tokens → product name
* Normalize product name

Handle:

* multi-line product names
* noise tokens (brand names, units)
* malformed rows (skip safely)

---

## 4. Product Mapping Engine

### Logic:

IF mapping exists in DB:
→ use mapped Zoho item

ELSE:
→ perform fuzzy matching using `rapidfuzz`
→ return top matches
→ user selects
→ save mapping

---

## 5. Business Rules

Implement:

* Price change detection:
  compare with last stored price

* MRP change detection:
  compare historical values

* New product detection:
  if mapping not found

* Do NOT block processing — only highlight

---

## 6. UI (Critical for usability)

Build a **review screen**:

Table columns:

* Product name (editable dropdown)
* Quantity
* Rate
* Status (color-coded)

Status:

* ✅ Normal
* ⚠ Price change
* 🔴 New product

Actions:

* Select product mapping
* Remove line
* Confirm invoice

Must be:

* clean
* minimal
* usable by non-technical users

---

## 7. Zoho Integration

Use HTTP calls to Zoho Books API.

Implement:

* Fetch items → store in `product_cache`
* Create purchase bill after confirmation

Ensure:

* store Zoho item_id (not just name)
* handle API errors gracefully

---

## 8. Sync Mechanism

Implement:

Manual Sync:

* Button in UI
* Fetch all items from Zoho
* Replace product_cache

Auto Sync:

* Weekly job using APScheduler

---

## 9. Database Schema (MongoDB)

Collections:

### product_cache

* zoho_item_id
* name
* last_synced_at

### product_mapping

* vendor
* vendor_product_name
* zoho_item_id

### price_history

* zoho_item_id
* price
* mrp
* date

### invoices

* invoice_number
* vendor
* date
* status

---

## 10. Validation & Safety

* Prevent duplicate invoices (check invoice_number)
* Validate numeric fields (qty, rate)
* Skip malformed rows safely
* Log all parsing errors

---

## 11. Error Handling

* If parsing fails → show raw data to user
* If Zoho API fails → retry or show error
* Never lose user-confirmed data

---

## 12. Performance Requirements

* Process invoice in < 5 seconds
* No blocking UI
* Cache Zoho items locally

---

## 13. Development Phases

Phase 1:

* Upload + extract text

Phase 2:

* Parse items correctly

Phase 3:

* Sync Zoho items

Phase 4:

* Mapping + UI

Phase 5:

* Price detection

Phase 6:

* Create bill

---

## 14. Non-Goals (Do NOT implement)

* Multi-vendor support
* Multi-company support
* Real-time syncing
* AI-heavy pipelines
* Microservices

---

# 🧠 Engineering Principles

* Prefer **simple + deterministic logic**
* Fail gracefully
* Log everything important
* Build for clarity over cleverness
* Optimize only after correctness

---

# 🎯 Output Expectation

Deliver:

1. Clean backend structure
2. Working parsing logic for Milky Mist invoices
3. Simple UI for review
4. Working Zoho bill creation
5. Persistent mapping system

The system should be **stable, understandable, and easy to extend later**.

---
