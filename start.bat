@echo off
echo ============================================
echo  Vital Health Global -- Sales AI
echo ============================================
echo.

cd /d "C:\Users\Ola\healthsales"

if not exist ".env" (
    echo .env file missing! Please create it from .env.example
    pause
    exit /b 1
)

:: Kill anything already on port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING" 2^>nul') do (
    echo Stopping old server (PID %%a)...
    taskkill /PID %%a /F >nul 2>&1
)

echo Starting server on http://localhost:8000
echo Press Ctrl+C to stop.
echo.

:: Open browser after 2 seconds
ping -n 3 127.0.0.1 >nul
start "" http://localhost:8000

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
