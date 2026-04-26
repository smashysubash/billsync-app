# BillSync 📄💼

BillSync is a high-precision invoice automation system designed to streamline the workflow of converting vendor PDF invoices (starting with Milky Mist) into purchase bills in Zoho Books.

## 🎯 Objective
Automate the extraction of line items from PDF invoices, match them to existing Zoho Books items using fuzzy logic, and allow for human review before creating official records in your accounting software.

---

## 🚀 Features
- **Deterministic & OCR Extraction:** Primary parsing using `pdfplumber` for text-based PDFs and `PaddleOCR` as an intelligently-routed fallback for scanned documents.
- **Intelligent Product Matching:** Uses `rapidfuzz` (token set ratio) to suggest Zoho items for new vendor products. Mappings are "learned" and auto-saved for future invoices.
- **Anomaly Detection:** Automatically flags price changes or MRP mismatches compared to historical data stored in MongoDB.
- **Human-in-the-Loop:** A premium dark-mode React UI for reviewing, correcting, and confirming invoices before they hit your books.
- **Zoho Books Integration:** Secure OAuth2 integration for real-time item syncing and automated bill creation.
- **Stateless Backend with Cache:** MongoDB Atlas acts as a fast cache for mappings and price history, while Zoho Books remains the source of truth.

---

## 🛠 Tech Stack
- **Backend:** FastAPI (Python 3.12)
- **Frontend:** React (Vite, Vanilla CSS)
- **Database:** MongoDB Atlas
- **OCR/PDF:** PaddleOCR, Poppler, PyMuPDF
- **Infrastructure:** Docker & Docker Compose

---

## ⚙️ Getting Started

### 1. Prerequisites
- Docker and Docker Compose installed.
- A Zoho Books account and API credentials (Client ID, Secret, Refresh Token).
- A MongoDB Atlas connection string.

### 2. Configuration
Copy the template and fill in your credentials:
```bash
cp .env.example .env
```
Edit `.env` with:
- `MONGO_URI`: Your Atlas connection string.
- `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`, `ZOHO_ORGANIZATION_ID`.

### 3. Launch
```bash
docker-compose up --build
```
- **Frontend:** [http://localhost:5173](http://localhost:5173)
- **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 📋 Usage Flow
1. **Sync Items:** Click "Sync Zoho Items" in the UI to seed your local cache with your latest Zoho inventory.
2. **Upload:** Drag and drop a Milky Mist PDF invoice into the dashboard.
3. **Review:** 
   - Check the auto-matched products.
   - For **New Products** (🔴), select the correct Zoho item from the dropdown. This mapping is saved immediately for future use.
   - Watch for **Price Changes** (⚠) highlighted by the system.
4. **Confirm:** Click "Confirm & Create Bill" to push the purchase bill to Zoho Books.

---

## 🏗 Project Structure
```text
.
├── backend/            # FastAPI service
│   ├── main.py         # API entry point & routes
│   ├── parser.py       # Invoice parsing logic
│   ├── matcher.py      # Fuzzy matching engine
│   ├── zoho.py         # Zoho Books API client
│   └── db.py           # MongoDB connection & schemas
├── frontend/           # React SPA
│   ├── src/pages/      # Upload and Review views
│   └── src/api.js      # Backend communication layer
├── docker-compose.yml  # Orchestration
└── .env.example        # Environment template
```

## ⚖️ Constraints
- Designed for **Milky Mist** invoice formats.
- Human review is **mandatory** before record creation.
- MongoDB is a cache; always rely on Zoho for final balances.
