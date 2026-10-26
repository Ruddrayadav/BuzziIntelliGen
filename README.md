# BizIntel — Local Business Intelligence for Small Businesses

BizIntel is a private, local business intelligence platform built for small business owners (cafes, restaurants, retail shops). It ingests messy sales, expenses, and cashbook spreadsheets (CSV and Excel formats), cleans and standardises the data through a deterministic Python service layer, stores records in an isolated multi-tenant SQLite database, and presents insights through an interactive React dashboard and an offline "Ask AI" assistant powered by local Ollama LLMs.

```
+-----------------------------------------------------------------------------------+
|                            [ BizIntel Dashboard ]                                 |
|   +-------------------+  +-------------------+  +-------------------+             |
|   |  Total Revenue    |  |  Total Expenses   |  |    Net Profit     |             |
|   |     $27,530       |  |     $285,199      |  |    -$257,669      |             |
|   +-------------------+  +-------------------+  +-------------------+             |
|   [ Overview ]   [ Comparison ]   [ Anomalies ]   [ Diagnostics ]   [ Ask AI ]    |
|   -----------------------------------------------------------------------------   |
|   * Revenue Waterfall Chart      * Day-of-Week Velocity     * Slow Mover Analysis |
+-----------------------------------------------------------------------------------+
```

### Architecture in 5 Lines
- **Frontend**: React 18 SPA built with Vite, TypeScript, Tailwind CSS, and Recharts, served via Nginx.
- **Backend API**: FastAPI running asynchronous REST endpoints with signed, HTTP-only session authentication cookies.
- **Service Layer**: Pure Python pipelines for format detection, fuzzy column mapping, deduplication, and anomaly analytics.
- **Database**: SQLite (`data/biz_intelligence.db`) with per-tenant isolation for zero-configuration, secure local storage.
- **Local AI**: Ollama engine hosting open-weight models (`gemma3:4b`) for natural language SQL-free querying and explanation.

---

## Run with Docker

Run the complete BizIntel stack (Web UI, FastAPI backend, Ollama service, and automatic model provisioner) with a single command.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- **RAM**: Minimum 8 GB available
- **Disk**: Minimum 6 GB free disk space (includes container images and the 3.3 GB local LLM)

### Quickstart
```bash
git clone <repo> && cd <repo>
docker compose up --build
```

1. Open **[http://localhost:8080](http://localhost:8080)** in your browser.
2. Register a new business account (e.g. username `demo`, password `password123`).
3. Navigate to **Upload** and import the sample files located in `data/samples/`:
   - `data/samples/sample_sales.csv`
   - `data/samples/sample_expenses.csv`
4. **Expected verification metrics**:
   - **Total Revenue**: `27,530`
   - **Total Expenses**: `285,199`

> **Note on First Startup**: The `ollama-pull` service automatically downloads the ~3.3 GB `gemma3:4b` model in the background. The web application, data cleaning, and dashboards are immediately functional. If you navigate to **Ask AI** before the download finishes, the app gracefully displays: *"The AI model is still starting or not running. Try again in a minute."*

---

## Run without Docker

If you prefer to run services directly on your host machine without containerization, automated start scripts handle all dependencies, virtual environments, and configuration.

### Prerequisites & Downloads
- **Python 3.11+**: [Download Python](https://www.python.org/downloads/)
- **Node.js 18+ & npm**: [Download Node.js](https://nodejs.org/)
- **Ollama**: [Download Ollama](https://ollama.com/download)

### One-Line Start Command
- **macOS / Linux**:
  ```bash
  ./start.sh
  ```
- **Windows**:
  ```cmd
  start.bat
  ```

The start scripts automatically:
1. Verify required runtimes (Python, Node, npm, Ollama) and display download links if missing.
2. Initialize `venv` and run `pip install` only when `requirements.txt` changes.
3. Run `npm install` inside `frontend/` only when packages or lockfiles change.
4. Generate a unique `BIZINTEL_SESSION_SECRET` inside `.env` if not present.
5. Launch the Ollama daemon and pull `gemma3:4b` if not already installed.
6. Check that ports `8000` and `5173` are free, launch backend and frontend servers, and open `http://localhost:5173`.
7. Handle `Ctrl+C` to terminate background processes cleanly.

### Manual Commands
If you wish to run the processes in separate terminal windows:

**Terminal 1 — Local AI (Ollama)**:
```bash
ollama serve
ollama pull gemma3:4b
```

**Terminal 2 — FastAPI Backend**:
```bash
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload --env-file .env --port 8000
```

**Terminal 3 — React Frontend**:
```bash
cd frontend
npm install
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)**. API Swagger docs are accessible at **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## Troubleshooting

- **Port Already in Use**:
  - *Docker (Port 8080)*: If port 8080 is occupied, stop conflicting containers or alter the host port in `docker-compose.yml` (e.g. `"8081:80"`).
  - *No-Docker (Ports 8000 or 5173)*: The start script identifies occupied ports directly. Identify and stop the occupying process:
    ```bash
    # macOS/Linux
    lsof -i :8000
    kill -9 <PID>
    # Windows
    netstat -ano | findstr :8000
    taskkill /PID <PID> /F
    ```
- **Model Still Downloading (HTTP 503)**:
  - Downloading `gemma3:4b` (~3.3 GB) depends on internet speed. Check progress:
    - Docker: `docker compose logs -f ollama-pull`
    - No-Docker: `ollama list`
- **Low Memory / Out of Memory**:
  - Ollama requires ~4.5 GB of RAM when active. If Docker exits with code 137, increase RAM allocation in **Docker Desktop Settings -> Resources -> Memory** to 8 GB.
- **Resetting All Application Data**:
  - To erase all uploaded files and user databases:
    ```bash
    # Docker
    docker compose down -v
    rm -rf data/biz_intelligence.db* data/uploads/*

    # No-Docker
    rm -f data/biz_intelligence.db* data/uploads/*
    ```
- **Windows WSL2**:
  - Ensure Docker Desktop is configured to use the **WSL 2 backend** under **Settings -> General**. Run scripts inside PowerShell, CMD, or your WSL2 Ubuntu terminal.

---

## Test Files and Fixtures

The directory `tests/fixtures/` contains test files designed to evaluate real-world spreadsheet challenges:
- `1_messy_sales.csv`: Tests handling of missing dates, non-numeric revenue strings, and negative order quantities without crashing.
- `2_messy_expenses.csv`: Tests handling of unmapped categories and corrupt monetary amounts.
- `3_category_variants.csv`: Evaluates deduplication and fuzzy merging of variant expense categories (e.g. `Raw Material` vs `raw materials`).
- `4_new_category_*`: Tests period-over-period comparative logic when entirely new product lines or expense categories appear.
- `5_cashbook.csv`: Tests automatic single-file cashbook detection and debit/credit splitting into separate sales and expenses.
- `6_shop_sales.csv` & `6_shop_expenses.csv`: Tests alternate currency formats (₹, commas) and international date formats (`DD/MM/YYYY`).
- `7_formula_names.csv`: Tests CSV injection protection (formula prefixes neutralized on export).
- `8_exact_duplicate_rows.csv`: Tests that true repeat purchases (identical orders) are preserved while duplicate corrupted uploads are filtered.
- `9_sales.xlsx`: Tests legacy and modern multi-sheet Excel parsing.

See [tests/fixtures/EXPECTED.md](file:///Users/rudrayadav/Downloads/Rudra%20File%27s/Final%20Year%20Project/tests/fixtures/EXPECTED.md) for expected benchmark values for each fixture.

Run the automated test suite at any time:
```bash
pytest -q
```

---

## Limitations and Future Scope

1. **Supplier Invoices & Payment Reminders**: Currently, the platform records point-in-time transactions. Future versions will support invoice parsing, due date scheduling, and supplier debt aging tables.
2. **PostgreSQL & Gemini API Switch**: The current architecture is optimized for zero-footprint local execution using SQLite and Ollama. A production cloud configuration can swap `DB_URL` to managed PostgreSQL and integrate Google Gemini API via an environment toggle.
3. **Alembic Database Migrations**: Schema updates currently run via SQLAlchemy metadata reflection on startup. Production deployment should adopt Alembic for versioned database schema migrations.
4. **Distributed Rate Limiting**: The authentication brute-force limiter currently tracks failed login attempts in an in-memory dictionary. Moving to Redis or database-backed tracking will allow horizontal scaling.
5. **Refunds & Credit Notes**: Negative transactions are currently quarantined during data ingestion. Supporting formal credit notes and partial returns is scheduled for the next release.
