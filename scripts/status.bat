@echo off
chcp 65001 >nul
REM =============================================================================
REM AI Agent 服务状态查看脚本 (Windows)
REM =============================================================================

setlocal enabledelayedexpansion

echo ==========================================
echo AI Agent 服务状态
echo ==========================================

REM 检查 gunicorn 进程
tasklist /FI "IMAGENAME eq gunicorn.exe" 2>nul | findstr /i "gunicorn" >nul
if not errorlevel 1 (
    echo [RUNNING] Gunicorn 正在运行
    tasklist /FI "IMAGENAME eq gunicorn.exe"
) else (
    echo [STOPPED] Gunicorn 未运行
)

echo.

REM 检查端口
netstat -ano | findstr ":8080" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [LISTENING] 端口 8080:
    netstat -ano | findstr ":8080" | findstr "LISTENING"
) else (
    echo [STOPPED] 端口 8080 未监听
)

echo.

REM 内存使用
echo [MEMORY] Python 进程内存使用:
wmic process where "name='python.exe' or name='pythonw.exe'" get ProcessId,WorkingSetSize,Name 2>nul | findstr /i "python"

echo.

REM 检查日志
if exist "%~dp0logs\error.log" (
    echo [LOG] 最近错误日志 (最后10行):
    powershell -command "Get-Content '%~dp0logs\error.log' -Tail 10"
) else (
    echo [LOG] 无错误日志
)

pause
