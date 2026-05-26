@echo off
chcp 65001 >nul
REM =============================================================================
REM AI Agent 服务启动脚本（2核4G 优化版 - Windows）
REM =============================================================================

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo ==========================================
echo AI Agent 服务启动（2核4G 优化配置）
echo ==========================================

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 未安装
    exit /b 1
)

REM 加载环境变量
if exist "%PROJECT_DIR%.env" (
    echo [INFO] 加载环境变量...
    for /f "usebackq tokens=*" %%a in ("%PROJECT_DIR%.env") do (
        set "LINE=%%a"
        if not "!LINE:~0,1!"=="#" (
            for /f "tokens=1,2 delims==" %%b in ("!LINE!") do (
                set "%%b=%%c"
            )
        )
    )
)

REM 默认配置
if not defined DB_POOL_SIZE set "DB_POOL_SIZE=3"
if not defined DB_MAX_OVERFLOW set "DB_MAX_OVERFLOW=5"
if not defined WS_MAX_CONNECTIONS set "WS_MAX_CONNECTIONS=50"
if not defined LOG_LEVEL set "LOG_LEVEL=INFO"

echo [INFO] 数据库连接池: %DB_POOL_SIZE% ^(溢出: %DB_MAX_OVERFLOW%^)
echo [INFO] WebSocket 最大连接: %WS_MAX_CONNECTIONS%
echo [INFO] 日志级别: %LOG_LEVEL%
echo ==========================================

REM 创建日志目录
if not exist "%PROJECT_DIR%logs" mkdir "%PROJECT_DIR%logs"

REM 检查端口
netstat -ano | findstr ":8080" >nul
if not errorlevel 1 (
    echo [WARN] 端口 8080 已被占用
    set /p CHOICE="是否关闭现有进程? (y/n): "
    if /i "!CHOICE!"=="y" (
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080" ^| findstr "LISTENING"') do (
            taskkill /F /PID %%a >nul 2>&1
        )
        timeout /t 2 >nul
    )
)

REM 启动模式
set "START_MODE=%~1"
if not defined START_MODE set "START_MODE=gunicorn"

if "!START_MODE!"=="dev" (
    echo [INFO] 以开发模式启动 (uvicorn)...
    start "AI-Agent-Dev" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload"
) else (
    echo [INFO] 以生产模式启动 (gunicorn)...

    REM 检查 gunicorn
    pip show gunicorn >nul 2>&1
    if errorlevel 1 (
        echo [INFO] 安装 gunicorn...
        pip install gunicorn
    )

    start "AI-Agent" cmd /k "gunicorn app.main:app --bind 0.0.0.0:8080 --workers 2 --threads 2 --worker-class uvicorn.workers.UvicornH11Worker --timeout 120 --log-level info"

    timeout /t 3 >nul

    REM 检查是否启动成功
    curl -s http://127.0.0.1:8080/health >nul 2>&1
    if not errorlevel 1 (
        echo [INFO] 服务启动成功!
        echo [INFO] 访问地址: http://127.0.0.1:8080
    ) else (
        echo [WARN] 服务可能未完全启动，请检查日志
    )
)

echo.
echo [INFO] 常用命令:
echo   start.bat dev        - 开发模式启动
echo   start.bat gunicorn   - 生产模式启动
echo   stop.bat             - 停止服务
echo   scripts\status.bat   - 查看服务状态
echo.
pause
