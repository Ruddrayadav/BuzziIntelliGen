# PROGRESS.md
# BizIntel — AI-Powered Business Intelligence System
# Last updated: 2026-10-02

---

## ✅ Done

### Step 1A — Foundation (2026-10-02)
- Created full folder skeleton: `app/`, `services/`, `db/`, `llm/`, `data/`, `tests/`
- `config.py` — central settings with Pydantic BaseSettings; swap model/DB by editing one line
- `requirements.txt` — all dependencies pinned with comments explaining WHY each exists
- `data/samples/sample_sales.csv` — intentionally messy: ₹ symbols, duplicate rows, inconsistent casing, mixed date formats, blank cells, missing order_ids
- `data/samples/sample_expenses.csv` — intentionally messy: same issues, inconsistent category names, amounts with commas
- `main.py` — minimal Streamlit shell (navigation only, no logic)

---

### Step 1B — Database Models (2026-10-02)
- `db/models.py` — UploadLog, Sales, Expenses tables with tenant_id on every row
- `db/database.py` — engine, SessionLocal, get_db() context manager, init_db(), health_check()
- SQLite WAL mode + foreign key enforcement via PRAGMA
- Composite index on (tenant_id, date) for fast range queries
- Tenant isolation verified: wrong tenant_id returns None

---

### Step 1C — Cleaning Service (2026-10-02)
- `services/cleaning_service.py` — full pipeline: _parse_money, _parse_date, _normalize_text, clean_sales, clean_expenses, clean_dataframe
- `tests/test_cleaning.py` — 48 tests, all passing in 0.63s
- CleaningResult dataclass carries clean_df + report back to caller
- Row-level deduplication intentionally removed (identical sales/expenses on the same day are valid retail transactions)
- Invalid row rejection tracking with audit trail in `rejected_rows` table


---

### Step 1D — Mapping Service + LLM Wrapper (2026-10-02)
- `llm/llm.py` — call_llm (plain text), call_llm_json (JSON extraction with fallback), LLMError, is_llm_available
- `services/mapping_service.py` — rule-based alias matching for both file types, LLM fallback for ambiguous cols, security sanitisation, ColumnMapping dataclass
- `tests/test_mapping.py` — 39 tests all passing; LLM path tested with mocks (no Ollama needed)
- Full pipeline verified: suggest → apply → clean runs end-to-end
- Running total: **87 tests, all passing**

---

### Step 1E — Upload Service (2026-10-02)
- `services/upload_service.py` — two-phase design: suggest (Phase A, no DB) + execute (Phase B, atomic DB write)
- `tests/test_upload_service.py` — 27 tests, all passing
- Full pipeline verified end-to-end: file bytes → DB rows, tenant isolation, spot-check revenue value
- Running total: **114 tests, all passing in < 1 second**

---

### Step 1F — Upload UI (2026-10-02) — PHASE 1 COMPLETE ✅
- `app/pages/01_upload.py` — 4-stage upload page; UI Rule enforced: only st.* calls and service calls
- `app/pages/02_dashboard.py` — placeholder with live row-count check
- `app/pages/03_ask.py` — placeholder with Phase 4 feature preview
- `main.py` — st.navigation() with 3 pages, st.cache_resource for one-time DB init

**Phase 1 final score: 114 tests, all passing, < 1 second**

---

## 🔄 In Progress

### Phase 2 — Dashboard (2026-10-02) — PHASE 2 COMPLETE ✅
- `services/dashboard_service.py` — Database queries with SQLAlchemy and Pandas for KPI grouping (AOV, revenue, expenses)
- `tests/test_dashboard.py` — Unit tests for DB aggregations
- `app/pages/02_dashboard.py` — Beautiful, interactive UI using Plotly charts (no data logic)

---

## 🔄 In Progress

### Phase 3 — LLM Analytics (2026-10-02) — PHASE 3 COMPLETE ✅
- `services/ai_service.py` — Intent Routing architecture (identify intent -> query DB -> explain data) to guarantee 100% accuracy.
- `app/pages/03_ask.py` — Streamlit chat UI using `st.chat_message` and `st.session_state` to retain chat history.
- `tests/test_ai_service.py` — Mocked LLM responses to ensure query routing works quickly and cleanly.

**Current Test Score: 121 tests, all passing**

---

## 📋 Upcoming

### Phase 4 — Data Persistence & Isolation (2026-10-02) — PHASE 4 COMPLETE ✅
- `db/models.py` — Added User table mapping `username` to `tenant_id`.
- `services/auth_service.py` — Built secure login/registration with SHA-256 hashing and salting.
- `app/pages/00_login.py` — Added a login/register UI that blocks access to the rest of the app until authenticated.
- All services and pages now dynamically use the logged-in user's `tenant_id` from `st.session_state`.
- **Phase 4 Test Score: 125 tests, all passing**

---

### Phase 5 — Advanced Analytics & Decision Support (2026-10-14) — PHASE 5 COMPLETE ✅
- `services/analytics_service.py` — High-performance analytics engine:
  1. **Period-over-Period Comparison (MoM / Custom Range)**: Compares any two reporting months with revenue, expense, profit, order, and AOV deltas + product gainers & decliners + expense category shifts.
  2. **Automated Statistical Anomaly Detection**: Dual-scale rolling baseline & global Z-score anomaly detector for daily revenue drops/spikes and unexpected operational cost surges with severity tags (Critical, Warning, Info).
  3. **Root Cause Profit Drop & Margin Diagnostics**: Mathematical decomposition into Revenue Contraction vs Expense Inflation vs Dual Drag, identifying top product drags and surging cost drivers + actionable business recommendations + Plotly waterfall chart data.
- `app/pages/02_dashboard.py` — Elevated Executive Dashboard with 4 interactive tabs:
  - 📊 **Executive Overview**: Real-time KPIs, daily revenue trendline, top 5 products, and expense donut.
  - 🔄 **Period Comparison (MoM)**: Dynamic month selector, comparative delta metrics, product shift charts, and category breakdown.
  - 🚨 **Anomaly Radar**: Alert counts, interactive daily timeline with overlaid outlier markers, and detailed audit log.
  - 🔍 **Profit Diagnostics**: Primary causal driver banner, Plotly waterfall attribution bridge, and root-cause product/cost tables.
- `services/ai_service.py` & `app/pages/03_ask.py` — Integrated 3 new intents (`period_comparison`, `anomaly_detection`, `profit_diagnosis`) with instant prompt chips and source data audit tables.
- `tests/test_analytics.py` — 9 new unit tests covering period comparison, anomaly detection (spikes & drops), and profit diagnosis.
- **Current Test Score: 140 tests, all passing in 1.10s**

### Phase 0 — Fix Known Bugs (2026-10-14)
- **Step 0.0 — Test DB Isolation & Safety**:
  - `tests/conftest.py` — intercepts database initialization; directs all pytest runs to an isolated temporary SQLite database so developer's live `data/biz_intelligence.db` is never modified or wiped by test suites.
  - Removed `scratch/` from git tracking and updated `.gitignore` with `*.db` patterns.
- **Step 0.1 — Frontend & API Bug Fixes**:
  - Backend trend granularity endpoint (`/api/dashboard/trend?granularity=daily|weekly|monthly`) in `services/dashboard_service.py` and `api/routes/dashboard.py`. Groups by real ISO calendar weeks (`W01 2024`) and months, moving grouping logic out of frontend (Principle 5).
  - Frontend KPI cards: clearly separates latest reporting month figures from all-time totals with explicit labels so owners are never misled.
  - Expense delta inversion: expense surges are styled red/unfavorable, and expense reductions are green/favorable.
  - Dynamic upload mapping validation: recomputes missing required fields as owner maps columns, warns on duplicate target fields, and disables "Import files" until mapping is clean.
  - Excel/CSV formula injection protection: neutralizes cells starting with `=`, `+`, `-`, or `@` by prefixing an apostrophe on CSV download.
  - **Test Score: 146 tests, all passing**
- **Step 0.2 — Backend Upload Safety & Deduplication**:
  - SHA-256 deduplication per tenant: computes SHA-256 hash of uploaded file bytes; detects identical duplicate uploads and returns HTTP 409 Conflict with informative timestamp and filename.
  - Safe replacement (`mode="replace"` / `replace=True`): atomically deletes previous `UploadLog` and cascades deletion of previous sales, expenses, and rejected rows within the same transaction before writing the fresh import.
  - Server-side mapping validation: `validate_confirmed_mapping()` in `services/mapping_service.py` strictly verifies standard target fields, blocks duplicate target assignments, and enforces all required fields before processing data.
  - Content-Length & memory protection: upfront check of `Content-Length` header rejects > 10MB payloads with HTTP 413, and streaming chunk reader protects against memory exhaustion.
  - Transparent SQLite migration: `init_db()` automatically inspects `upload_log` and adds nullable `file_hash` column and index without touching existing data.
  - Frontend conflict resolution: modal banner displays 409 Conflict warning with options to skip or replace existing import.
  - **Test Score: 159 tests, all passing**
- **Step 0.3 — File Detector Rewrite & Cash-Book Splitting**:
  - Regex word boundary detector (`\b`) with underscore/hyphen normalization: prevents substring collisions (e.g. "rent" inside "current" or "parent", "cost" inside "customer").
  - Value-based heuristics: checks category/description column contents when headers are generic (e.g. `Date, Type, Details, Amount`) to reliably separate sales from expenses.
  - Cash-book file detection & automatic splitting: detects single files containing dual Debit/Credit columns, Inflow/Outflow type values, or signed (+/-) amounts; splits rows cleanly into Sales and Expenses without requiring double uploads.
  - Atomic cash-book ingestion: `execute_cashbook_upload()` records separate upload logs and inserts both sets of records within a single atomic database transaction with hash deduplication and replacement support.
  - Clean UI presentation: dedicated purple cash-book chip and split summary breakdown showing count and sum of split sales vs expenses.
  - **Test Score: 178 tests, all passing**
- **Step 0.4 — Ask AI Reliability & Analytics Guardrails**:
  - Distinct offline AI handling: when Ollama/LLM is unreachable, returns a clear `"The AI is not available right now"` state and HTTP 503 instead of the misleading `"I don't know how to answer that yet"`.
  - Graceful explanation degradation: if the AI language processor goes offline after data is computed, the verified SQL data table is returned directly with a plain note.
  - Strict month parameter validation: enforces `YYYY-MM` format via regex `^\d{4}-(0[1-9]|1[0-2])$` in `api/routes/analytics.py` (returning HTTP 422 for malformed or out-of-range dates like `2024-13` or `2024-5`).
  - Strict period comparison guardrails: `compare_periods` and `diagnose_profit_drop` require months that have BOTH sales and expense data. If a month has only sales or only expenses, returns HTTP 400 Bad Request with a clear, plain-language message (e.g. `"Month '2024-01' only has sales data (no expenses recorded). Comparison requires both sales and expenses."`) rather than generating distorted zero-cost comparisons.
  - Auto-selection of complete months: when comparing periods without explicit months, defaults only to periods that have both sales and expenses.
  - Frontend error clarity: `ApiError` captures FastAPI `detail` messages for friendly red alert banner display in Ask AI and Dashboard tabs.
  - **Test Score: 188 tests, all passing**
- **Step 0.5 — Auth Hardening & Production Reliability**:
  - Upgraded password hashing from raw SHA-256 to `hashlib.scrypt` ($n=16384, r=8, p=1, dklen=64$) in self-describing format (`scrypt$16384$8$1$<salt_hex>$<hash_hex>`) with `hmac.compare_digest`.
  - Transparent upgrade on login: authenticates legacy 64-character SHA-256 hashes and transparently re-hashes them to modern scrypt in the database without user interruption.
  - Enforced minimum 8-character password constraint across service (`register_user`) and API schema (`RegisterRequest`).
  - Rate limiting protection: 5 failed login attempts per username and client IP within a 10-minute sliding window triggers HTTP 429 Too Many Requests with a friendly wait message.
  - Environment-controlled cookie security: reads `BIZINTEL_COOKIE_SECURE` (`true`/`false`) for HTTPS production deployments.
  - Startup safety check: FastAPI startup aborts with a descriptive error if `BIZINTEL_SESSION_SECRET` is missing or still set to the insecure placeholder.
  - Cleaned developer paths in `README.md` and marked preview marketing metrics as `(Example)` on the landing page.
  - Model schema update: widened `User.password_hash` to `String(255)`.
  - **Test Score: 194 tests, all passing**

---

## 🏆 Project Achievements
The "AI-Powered Business Intelligence & Decision Support System for Small Businesses" now features enterprise-grade analytical intelligence:
1. Multi-tenant secure login and tenant isolation.
2. Excel/CSV upload with rule-based and AI-assisted column mapping & audit trail.
3. Automated data cleaning and rejected row auditing.
4. Interactive KPI Dashboard with ISO week & monthly trends, period comparisons, and waterfall profit diagnostics.
5. Period-over-Period (MoM) comparison with product gainers & decliners.
6. Statistical Anomaly Detection with rolling baselines.
7. Root Cause Profit Drop & Margin Diagnostics with waterfall attribution.
8. Hallucination-free Natural Language Q&A with intent routing.

| Phase 0 | Bug fixes: Chart grouping, KPI clarity, upload validation, auth hardening |
| Phase 1 | Immediate analytical wins: category breakdowns, unit volume, Ask AI v2 |
| Phase 2 | Decision support: Attention items, day-of-week intelligence, revenue targets |
| Phase 3 | Trust & output: Upload audit rollback, executive PDF reports, chat history |

---

## 🏛️ Key Decisions & Reasons

| Decision | Reason |
|----------|--------|
| SQLite now, PostgreSQL later | SQLite needs zero setup; SQLAlchemy abstracts the difference so switching is one config line |
| `gemma3:4b` as starting model | Locally available; `qwen3:4b` available as alternative; swap via `LLM_MODEL` in config |
| Pydantic BaseSettings for config | Settings are validated at startup; can be overridden by env vars for deployment |
| Service layer separate from UI | Streamlit UI and React UI consume the exact same Python service layer |
| LLM never calculates numbers | Prevents hallucinated numbers; all arithmetic is Python/SQL, LLM only explains |
| Relative dates resolved by code | "Last month" computed from latest date in user's data, not guessed by LLM |
| Isolated temp DB for pytest | Prevents test suites from altering or deleting rows in developer database |

---

## 🛠️ Environment

- Python: 3.11
- Ollama models: gemma3:4b (active), qwen3:4b (available)
- DB: SQLite (dev) → PostgreSQL (production)
- UI: React + TypeScript + Tailwind (FastAPI backend); Streamlit as fallback

