@echo off
chcp 65001 >nul
REM =============================================================================
REM AI Agent 日志查看脚本 (Windows)
REM =============================================================================

setlocal enabledelayedexpansion

set "LOG_TYPE=%~1"
if not defined LOG_TYPE set "LOG_TYPE=error"

if "%LOG_TYPE%"=="error" (
    echo ========== Error Log ==========
    if exist "%~dp0logs\error.log" (
        powershell -command "Get-Content '%~dp0logs\error.log' -Tail 100"
    ) else (
        echo 无错误日志
    )
) else if "%LOG_TYPE%"=="access" (
    echo ========== Access Log ==========
    if exist "%~dp0logs\access.log" (
        powershell -command "Get-Content '%~dp0logs\access.log' -Tail 100"
    ) else (
        echo 无访问日志
    )
) else if "%LOG_TYPE%"=="full" (
    echo ========== Full Error Log ==========
    if exist "%~dp0logs\error.log" (
        type "%~dp0logs\error.log"
    ) else (
        echo 无错误日志
    )
) else (
    echo 用法: logs.bat [error^|access^|full]
    echo   error  - 查看最近错误日志 (默认)
    echo   access - 查看最近访问日志
    echo   full   - 查看完整错误日志
    echo.
    if exist "%~dp0logs\error.log" (
        powershell -command "Get-Content '%~dp0logs\error.log' -Tail 50"
    ) else (
        echo 无错误日志
    )
)

pause
