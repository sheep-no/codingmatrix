# FastAPI Service Startup Script (PowerShell)
# Usage: .\start.ps1

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  FastAPI Service Startup (Windows PowerShell)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Python
Write-Host "[1/4] Checking Python environment..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  [Error] Python not found! Please install Python 3.10+" -ForegroundColor Red
    pause
    exit 1
}
Write-Host ""

# Step 2: Check dependencies
Write-Host "[2/4] Checking dependencies..." -ForegroundColor Yellow
if (Get-Module -ListAvailable -Name python-dotenv) {
    Write-Host "  python-dotenv is installed" -ForegroundColor Green
} else {
    Write-Host "  Installing python-dotenv..." -ForegroundColor Yellow
    pip install python-dotenv
}
Write-Host ""

# Step 3: Check .env file
Write-Host "[3/4] Checking configuration..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "  Found .env configuration file" -ForegroundColor Green
} else {
    Write-Host "  [Warning] .env file not found" -ForegroundColor Yellow
    Write-Host "  Please create .env file from .env.example" -ForegroundColor Yellow
}
Write-Host ""

# Step 4: Start service
Write-Host "[4/4] Starting FastAPI service..." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Service URL: http://localhost:8000" -ForegroundColor Green
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Green
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Start uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Write-Host ""
Write-Host "Service stopped" -ForegroundColor Yellow
pause
