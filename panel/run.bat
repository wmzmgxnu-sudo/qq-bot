@echo off
title Bot Management Panel

cd /d "%~dp0.."

echo ========================================
echo  Checking dependencies...
echo ========================================
.venv\Scripts\python.exe -c "import fastapi,uvicorn,python_dotenv" 2>nul
if errorlevel 1 (
    echo  Installing panel dependencies...
    .venv\Scripts\pip.exe install fastapi uvicorn python-dotenv -q
)

echo.
echo ========================================
echo  Bot Management Panel
echo ========================================
echo.
echo  Panel running at: http://localhost:30080
echo  Press Ctrl+C to stop
echo ========================================
echo.

.venv\Scripts\python.exe "%~dp0app.py"

pause