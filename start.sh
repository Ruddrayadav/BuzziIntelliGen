#!/usr/bin/env bash
set -eo pipefail

echo "===================================================="
echo " Starting BizIntel (No-Docker Mode)                "
echo "===================================================="

# Determine project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ------------------------------------------------------------------------------
# 1. Check prerequisites: Python (3.11+), Node (18+), npm, Ollama
# ------------------------------------------------------------------------------
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERROR: Python 3.11+ is required but not found."
    echo "Please download and install Python from: https://www.python.org/downloads/"
    exit 1
fi

if ! "$PYTHON_BIN" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
    PY_VER=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
    echo "ERROR: Python 3.11+ is required, but found Python $PY_VER."
    echo "Please download and install Python 3.11+ from: https://www.python.org/downloads/"
    exit 1
fi

if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: Node.js 18+ is required but not found."
    echo "Please download and install Node.js from: https://nodejs.org/"
    exit 1
fi

NODE_MAJOR=$(node -e "console.log(process.versions.node.split('.')[0])" 2>/dev/null || echo "0")
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "ERROR: Node.js 18+ is required, but found $(node -v)."
    echo "Please download and install Node.js 18+ from: https://nodejs.org/"
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm is required but not found."
    echo "Please download and install Node.js (which includes npm) from: https://nodejs.org/"
    exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
    echo "ERROR: Ollama is required for local AI features but not found."
    echo "Please download and install Ollama from: https://ollama.com/download"
    exit 1
fi

echo "✔ Prerequisites verified (Python, Node.js, npm, Ollama)."

# ------------------------------------------------------------------------------
# 2. Virtual environment and Python dependencies
# ------------------------------------------------------------------------------
if [ ! -d "venv" ] || [ ! -f "venv/bin/python" ]; then
    echo "Creating Python virtual environment in ./venv..."
    "$PYTHON_BIN" -m venv venv || {
        echo "ERROR: Failed to create Python virtual environment."
        exit 1
    }
fi

VENV_PYTHON="./venv/bin/python"
VENV_PIP="./venv/bin/pip"

CURRENT_REQ_HASH=$("$PYTHON_BIN" -c "import hashlib; print(hashlib.sha256(open('requirements.txt', 'rb').read()).hexdigest())")
STORED_REQ_HASH=""
if [ -f "venv/.req_hash" ]; then
    STORED_REQ_HASH=$(cat "venv/.req_hash" 2>/dev/null || true)
fi

if [ "$CURRENT_REQ_HASH" != "$STORED_REQ_HASH" ]; then
    echo "Installing/updating Python dependencies from requirements.txt..."
    "$VENV_PIP" install -r requirements.txt || {
        echo "ERROR: Failed to install Python dependencies."
        exit 1
    }
    echo "$CURRENT_REQ_HASH" > "venv/.req_hash"
    echo "✔ Python dependencies up to date."
else
    echo "✔ Python dependencies already satisfied."
fi

# ------------------------------------------------------------------------------
# 3. Frontend npm dependencies
# ------------------------------------------------------------------------------
LOCK_FILE="frontend/package-lock.json"
CURRENT_LOCK_HASH=""
if [ -f "$LOCK_FILE" ]; then
    CURRENT_LOCK_HASH=$("$PYTHON_BIN" -c "import hashlib; print(hashlib.sha256(open('$LOCK_FILE', 'rb').read()).hexdigest())")
fi

STORED_LOCK_HASH=""
if [ -f "frontend/node_modules/.lock_hash" ]; then
    STORED_LOCK_HASH=$(cat "frontend/node_modules/.lock_hash" 2>/dev/null || true)
fi

if [ ! -d "frontend/node_modules" ] || [ "$CURRENT_LOCK_HASH" != "$STORED_LOCK_HASH" ]; then
    echo "Installing frontend dependencies in ./frontend..."
    (cd frontend && npm install) || {
        echo "ERROR: Failed to install frontend npm packages."
        exit 1
    }
    if [ -n "$CURRENT_LOCK_HASH" ]; then
        echo "$CURRENT_LOCK_HASH" > "frontend/node_modules/.lock_hash"
    fi
    echo "✔ Frontend dependencies up to date."
else
    echo "✔ Frontend dependencies already satisfied."
fi

# ------------------------------------------------------------------------------
# 4. Environment file (.env) configuration
# ------------------------------------------------------------------------------
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    RANDOM_SECRET=$("$VENV_PYTHON" -c "import secrets; print(secrets.token_urlsafe(48))")
    "$VENV_PYTHON" -c "
import re
with open('.env', 'r') as f:
    content = f.read()
new_content = re.sub(r'BIZINTEL_SESSION_SECRET=.*', f'BIZINTEL_SESSION_SECRET=${RANDOM_SECRET}', content)
with open('.env', 'w') as f:
    f.write(new_content)
"
    echo "✔ Generated secure random session secret in .env."
else
    echo "✔ .env file exists."
fi

# ------------------------------------------------------------------------------
# 5. Make sure Ollama is running and model is available
# ------------------------------------------------------------------------------
LLM_MODEL_NAME=$("$VENV_PYTHON" -c "
import re
model = 'gemma3:4b'
try:
    with open('.env', 'r') as f:
        for line in f:
            m = re.match(r'^\s*LLM_MODEL\s*=\s*(.+)', line)
            if m:
                model = m.group(1).strip().strip('\"\'')
                break
except Exception:
    pass
print(model)
")

echo "Checking Ollama service..."
if ! ollama list >/dev/null 2>&1; then
    echo "Starting Ollama service (ollama serve)..."
    nohup ollama serve >/dev/null 2>&1 &
    OLLAMA_PID=$!
    
    # Wait for Ollama to become responsive
    STARTED=0
    for _ in $(seq 1 10); do
        sleep 1
        if ollama list >/dev/null 2>&1; then
            STARTED=1
            break
        fi
    done

    if [ "$STARTED" -ne 1 ]; then
        echo "ERROR: Ollama server could not be started automatically."
        echo "Please launch Ollama manually (or run 'ollama serve' in another terminal) and re-run start.sh."
        exit 1
    fi
    echo "✔ Ollama service started."
else
    echo "✔ Ollama service is already running."
fi

# Check if required model is present
if ! ollama list 2>/dev/null | grep -q "${LLM_MODEL_NAME%%:*}"; then
    echo "Model '$LLM_MODEL_NAME' not found locally. Pulling model now (this may take a few minutes)..."
    ollama pull "$LLM_MODEL_NAME" || {
        echo "ERROR: Failed to pull Ollama model '$LLM_MODEL_NAME'."
        exit 1
    }
    echo "✔ Model '$LLM_MODEL_NAME' is ready."
else
    echo "✔ Model '$LLM_MODEL_NAME' is available."
fi

# ------------------------------------------------------------------------------
# 6. Check ports and start backend & frontend
# ------------------------------------------------------------------------------
# Port 8000 check
if ! "$VENV_PYTHON" -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.bind(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
    echo "ERROR: Port 8000 is already in use by another process."
    echo "Please stop the process using port 8000 (such as an existing uvicorn server) and try again."
    exit 1
fi

# Port 5173 check
if ! "$VENV_PYTHON" -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.bind(('127.0.0.1', 5173)); s.close()" 2>/dev/null; then
    echo "ERROR: Port 5173 is already in use by another process."
    echo "Please stop the process using port 5173 (such as an existing Vite dev server) and try again."
    exit 1
fi

echo "Starting backend API (uvicorn) on http://127.0.0.1:8000..."
"$VENV_PYTHON" -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --env-file .env &
BACKEND_PID=$!

echo "Starting frontend web (Vite) on http://localhost:5173..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

# Trap Ctrl+C and exit signals for clean termination
cleanup() {
    echo ""
    echo "Shutting down BizIntel services..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    wait "$BACKEND_PID" 2>/dev/null || true
    wait "$FRONTEND_PID" 2>/dev/null || true
    echo "✔ BizIntel stopped cleanly."
    exit 0
}
trap cleanup INT TERM EXIT

echo "Waiting for services to respond..."
READY=0
for _ in $(seq 1 30); do
    if "$VENV_PYTHON" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/docs', timeout=1); urllib.request.urlopen('http://localhost:5173', timeout=1)" 2>/dev/null; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -eq 1 ]; then
    echo "===================================================="
    echo " BizIntel is ready!"
    echo " Frontend: http://localhost:5173"
    echo " Backend:  http://127.0.0.1:8000/docs"
    echo " Press Ctrl+C to stop all services."
    echo "===================================================="
    if command -v open >/dev/null 2>&1; then
        open http://localhost:5173 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open http://localhost:5173 2>/dev/null || true
    fi
else
    echo "WARNING: Services took longer than expected to respond. You can check http://localhost:5173 manually."
fi

# Wait for background processes
wait
