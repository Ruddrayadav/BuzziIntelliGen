@echo off
setlocal enabledelayedexpansion

echo ====================================================
echo  Starting BizIntel (No-Docker Mode) - Windows
echo ====================================================

cd /d "%~dp0"

:: -----------------------------------------------------------------------------
:: 1. Check prerequisites: Python (3.11+), Node (18+), npm, Ollama
:: -----------------------------------------------------------------------------
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python 3.11+ is required but not found in PATH.
    echo Please download and install Python from: https://www.python.org/downloads/
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python 3.11+ is required.
    echo Please download and install Python 3.11+ from: https://www.python.org/downloads/
    exit /b 1
)

where node >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js 18+ is required but not found in PATH.
    echo Please download and install Node.js from: https://nodejs.org/
    exit /b 1
)

node -e "const v = parseInt(process.versions.node.split('.')[0], 10); process.exit(v >= 18 ? 0 : 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js 18+ is required.
    echo Please download and install Node.js 18+ from: https://nodejs.org/
    exit /b 1
)

where npm >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: npm is required but not found in PATH.
    echo Please download and install Node.js (which includes npm) from: https://nodejs.org/
    exit /b 1
)

where ollama >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Ollama is required for local AI features but not found in PATH.
    echo Please download and install Ollama from: https://ollama.com/download
    exit /b 1
)

echo [OK] Prerequisites verified (Python, Node.js, npm, Ollama).

:: -----------------------------------------------------------------------------
:: 2. Virtual environment and Python dependencies
:: -----------------------------------------------------------------------------
if not exist "venv\Scripts\python.exe" (
    echo Creating Python virtual environment in venv...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to create virtual environment.
        exit /b 1
    )
)

set "VENV_PYTHON=venv\Scripts\python.exe"
set "VENV_PIP=venv\Scripts\pip.exe"

set "REQ_CHANGED=0"
%VENV_PYTHON% -c "import hashlib, os, sys; cur=hashlib.sha256(open('requirements.txt','rb').read()).hexdigest(); old=open('venv/.req_hash').read().strip() if os.path.exists('venv/.req_hash') else ''; sys.exit(0 if cur==old else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 set "REQ_CHANGED=1"

if "%REQ_CHANGED%"=="1" (
    echo Installing/updating Python dependencies from requirements.txt...
    %VENV_PIP% install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to install Python dependencies.
        exit /b 1
    )
    %VENV_PYTHON% -c "import hashlib; open('venv/.req_hash','w').write(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())"
    echo [OK] Python dependencies up to date.
) else (
    echo [OK] Python dependencies already satisfied.
)

:: -----------------------------------------------------------------------------
:: 3. Frontend npm dependencies
:: -----------------------------------------------------------------------------
set "NPM_CHANGED=0"
if not exist "frontend\node_modules" set "NPM_CHANGED=1"
if exist "frontend\package-lock.json" (
    %VENV_PYTHON% -c "import hashlib, os, sys; cur=hashlib.sha256(open('frontend/package-lock.json','rb').read()).hexdigest(); old=open('frontend/node_modules/.lock_hash').read().strip() if os.path.exists('frontend/node_modules/.lock_hash') else ''; sys.exit(0 if cur==old else 1)" >nul 2>&1
    if %ERRORLEVEL% neq 0 set "NPM_CHANGED=1"
)

if "%NPM_CHANGED%"=="1" (
    echo Installing frontend dependencies in frontend...
    cd frontend
    call npm install
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to install frontend npm packages.
        cd ..
        exit /b 1
    )
    cd ..
    if exist "frontend\package-lock.json" (
        %VENV_PYTHON% -c "import hashlib; open('frontend/node_modules/.lock_hash','w').write(hashlib.sha256(open('frontend/package-lock.json','rb').read()).hexdigest())" >nul 2>&1
    )
    echo [OK] Frontend dependencies up to date.
) else (
    echo [OK] Frontend dependencies already satisfied.
)

:: -----------------------------------------------------------------------------
:: 4. Environment file (.env) configuration
:: -----------------------------------------------------------------------------
if not exist ".env" (
    echo Creating .env from .env.example...
    copy .env.example .env >nul
    %VENV_PYTHON% -c "import re, secrets; content=open('.env','r').read(); sec=secrets.token_urlsafe(48); open('.env','w').write(re.sub(r'BIZINTEL_SESSION_SECRET=.*', f'BIZINTEL_SESSION_SECRET={sec}', content))"
    echo [OK] Generated random session secret in .env.
) else (
    echo [OK] .env file exists.
)

:: -----------------------------------------------------------------------------
:: 5. Make sure Ollama is running and model is available
:: -----------------------------------------------------------------------------
for /f "tokens=*" %%m in ('%VENV_PYTHON% -c "import re; m='gemma3:4b'; [globals().__setitem__('m', l.split('=')[1].strip().strip('\"\'')) for l in open('.env') if l.strip().startswith('LLM_MODEL=')]; print(m)"') do set "LLM_MODEL=%%m"
if "%LLM_MODEL%"=="" set "LLM_MODEL=gemma3:4b"

ollama list >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Starting Ollama service...
    start "" ollama serve
    timeout /t 3 /nobreak >nul
    ollama list >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        timeout /t 5 /nobreak >nul
    )
)

ollama list >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Ollama server could not be started automatically.
    echo Please start Ollama manually and re-run start.bat.
    exit /b 1
)
echo [OK] Ollama service running.

ollama list | findstr /i "%LLM_MODEL%" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Model %LLM_MODEL% not found. Pulling now (this may take a few minutes)...
    ollama pull %LLM_MODEL%
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to pull model %LLM_MODEL%.
        exit /b 1
    )
)
echo [OK] Model %LLM_MODEL% ready.

:: -----------------------------------------------------------------------------
:: 6. Check ports and start backend & frontend
:: -----------------------------------------------------------------------------
%VENV_PYTHON% -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.bind(('127.0.0.1', 8000)); s.close()" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Port 8000 is already in use by another process.
    echo Please stop the process using port 8000 and try again.
    exit /b 1
)

%VENV_PYTHON% -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.bind(('127.0.0.1', 5173)); s.close()" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Port 5173 is already in use by another process.
    echo Please stop the process using port 5173 and try again.
    exit /b 1
)

echo Starting BizIntel services...
start "BizIntel Backend API" %VENV_PYTHON% -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --env-file .env
cd frontend
start "BizIntel Frontend" npm run dev
cd ..

echo Waiting for services to respond...
%VENV_PYTHON% -c "import time, urllib.request; [time.sleep(1) for _ in range(30) if not (urllib.request.urlopen('http://127.0.0.1:8000/docs') and urllib.request.urlopen('http://localhost:5173'))]" >nul 2>&1

echo ====================================================
echo  BizIntel is running!
echo  Frontend: http://localhost:5173
echo  Backend:  http://127.0.0.1:8000/docs
echo ====================================================
start http://localhost:5173
