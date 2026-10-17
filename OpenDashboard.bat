@echo off
title GoogleUnlimited Dashboard
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py -3 "%~dp0dashboard.py" %*
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Source mode needs Python 3.11 or newer. The desktop installer includes Python.
        echo Install it from https://www.python.org/downloads/ and select "Add Python to PATH".
        echo Then open this launcher again.
    ) else (
        python "%~dp0dashboard.py" %*
    )
)
pause
