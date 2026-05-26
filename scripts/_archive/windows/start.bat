@echo off
chcp 65001 >nul 2>&1
setlocal

echo ============================================================
echo          FastAPI Backend Startup Script (Windows)
echo ============================================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [Error] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

echo [1/4] Checking Python environment...
python --version
echo.

REM Check and install python-dotenv
echo [2/4] Checking dependencies...
pip show python-dotenv >nul 2>&1
if errorlevel 1 (
    echo Installing python-dotenv...
    pip install python-dotenv
) else (
    echo python-dotenv is already installed
)
echo.

REM Check .env file
echo [3/4] Checking configuration...
if exist ".env" (
    echo Found .env configuration file
) else (
    echo [Warning] .env file not found
    echo Please create .env file from .env.example
    pause
)
echo.

REM Start the service
echo [4/4] Starting FastAPI service...
echo ============================================================
echo.
echo Service URL: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo Press Ctrl+C to stop the service
echo ============================================================
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

echo.
echo Service stopped
pause
