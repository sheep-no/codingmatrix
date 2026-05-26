@echo off
setlocal

echo ============================================================
echo   FastAPI Service Startup (Windows)
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found!
    pause
    exit /b 1
)

REM Check .env file
if exist ".env" (
    echo Found .env file
) else (
    echo Creating default .env file...
    copy /Y "..\workspace\.env" ".env"
    if errorlevel 1 (
        echo Error: Cannot create .env file
        echo Please download .env from workspace root
        pause
        exit /b 1
    )
)
echo.

REM Install dotenv if needed
pip show python-dotenv >nul 2>&1
if errorlevel 1 (
    echo Installing python-dotenv...
    pip install python-dotenv
)
echo.

REM Start service
echo Starting FastAPI service...
echo.
echo URL: http://localhost:8000
echo Docs: http://localhost:8000/docs
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

echo.
echo Service stopped
pause
