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
- Deduplication on (date, product, revenue) for sales; (date, category, amount) for expenses

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

---

## 🏆 Project Achievements
The "AI-Powered Business Intelligence & Decision Support System for Small Businesses" now features enterprise-grade analytical intelligence:
1. Multi-tenant secure login and tenant isolation.
2. Excel/CSV upload with rule-based and AI-assisted column mapping & audit trail.
3. Automated data cleaning and deduplication.
4. Interactive KPI Dashboard with Plotly charts and 4 executive analytical tabs.
5. Period-over-Period (MoM) comparison with product gainers & decliners.
6. Statistical Anomaly Detection with rolling baselines.
7. Root Cause Profit Drop & Margin Diagnostics with waterfall attribution.
8. Hallucination-free Natural Language Q&A with intent routing.

| Phase 1 | Foundation, DB models, Cleaning & Upload Services, Multi-tenancy |
| Phase 2 | Dashboard KPIs and trend charts (SQL only, no AI) |
| Phase 3 | Natural Language AI Service + Q&A intent router |
| Phase 4 | Authentication, Multi-user tenant isolation, SHA-256 security |
| Phase 5 | Period comparison · Anomaly detection · Profit drop diagnostics |
| Phase 6 | FastAPI wrapper · Executive PDF reports · Docker deployment |

---

## 🏛️ Key Decisions & Reasons

| Decision | Reason |
|----------|--------|
| SQLite now, PostgreSQL later | SQLite needs zero setup; SQLAlchemy abstracts the difference so switching is one config line |
| `gemma3:4b` as starting model | Locally available; `qwen3:4b` available as alternative; swap via `LLM_MODEL` in config |
| Pydantic BaseSettings for config | Settings are validated at startup; can be overridden by env vars for deployment |
| Service layer separate from UI | Streamlit UI can be replaced by FastAPI + React without rewriting any logic |
| LLM never calculates numbers | Prevents hallucinated numbers; all arithmetic is Python/SQL, LLM only explains |
| Relative dates resolved by code | "Last month" computed from latest date in user's data, not guessed by LLM |
| sqlglot for SQL validation | Safely parse and whitelist SELECT-only queries before running fallback SQL |

---

## 🛠️ Environment

- Python: 3.11
- Ollama models: gemma3:4b (active), qwen3:4b (available)
- DB: SQLite (dev) → PostgreSQL (production)
- UI: Streamlit → FastAPI + React (future)
