@echo off
echo ============================================
echo  NaturalWell Health Sales AI — Setup
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause & exit /b 1
)

REM Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate and install
call venv\Scripts\activate
echo Installing dependencies (this takes 1-2 minutes)...
pip install -q -r requirements.txt
pip install -q pydantic-settings

REM Create .env if it doesn't exist
if not exist ".env" (
    copy .env.example .env
    echo.
    echo IMPORTANT: Edit .env with your API keys before starting!
    echo    Notepad .env
    echo.
)

echo.
echo ============================================
echo  Setup complete!
echo  Next: Edit .env with your API keys, then
echo  run start.bat to launch the application.
echo ============================================
pause
