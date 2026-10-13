# BizIntel

BizIntel is a local business-intelligence app for small businesses such as cafes, restaurants, and shops. It imports CSV/Excel sales and expense files, cleans them through the existing Python service layer, and presents the results in a React website. The original Streamlit app remains available as a fallback.

## What you can do

- Create a separate account for each business.
- Import sales and expense CSV, XLSX, or XLS files.
- Check detected columns and correct a mapping before import.
- View revenue, expenses, profit, products, unusual days, and month comparisons.
- Ask questions in plain language and see the source table behind each answer.

## First-time setup

You need Python 3.11+, Node.js 20+, npm, and [Ollama](https://ollama.com/) for the Ask AI feature.

```bash
cd "/Users/rudrayadav/Downloads/Rudra File's/Final Year Project"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and replace `BIZINTEL_SESSION_SECRET` with a long random value. The example file is safe to commit; `.env` is ignored by Git.

## Run the website

Open three terminals from the project folder.

Terminal 1 — local AI:

```bash
ollama pull gemma3:4b
ollama serve
```

Terminal 2 — FastAPI backend:

```bash
source venv/bin/activate
uvicorn api.main:app --reload --env-file .env
```

Terminal 3 — React frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. API documentation is available at http://127.0.0.1:8000/docs.

## Streamlit fallback

The original user interface is still available:

```bash
source venv/bin/activate
streamlit run main.py
```

## Tests and build checks

```bash
source venv/bin/activate
pytest -q

cd frontend
npm run build
```

## Important design choices

- The browser never sends a tenant ID. FastAPI reads it from the signed, `httpOnly` session cookie.
- The API calls existing services; calculations and database queries stay in the service layer.
- The Daily/Weekly/Monthly chart switch only groups already-returned daily values for display. That grouping is marked for a later backend move.
- Uploads are stateless: the API reads the selected file again when the owner confirms import.

## Supported files

CSV (`.csv`), Excel (`.xlsx`), and legacy Excel (`.xls`) files are supported. PDF and plain-text files are intentionally not listed because the current service layer does not safely parse them into business rows.
