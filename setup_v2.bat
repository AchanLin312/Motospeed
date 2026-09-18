@echo off
rem ============================================================
rem Motospeed V2 one-click setup: create venv + install deps
rem Requirements on this machine: Python 3.10+ (3.12+ recommended)
rem Run this ONCE after cloning the repository. After setup,
rem use start_v2.bat (copy from start_v2.example.bat) to launch.
rem ============================================================
setlocal
cd /d "%~dp0"

echo ============================================
echo   Motospeed V2 - one-click setup
echo ============================================
echo.

rem --- 1. locate Python
set "PY="
python --version >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
) else (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    echo [ERROR] Python not found. Install Python 3.10+ from
    echo         https://www.python.org/downloads/
    echo         and check "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)
echo [1/3] Found Python:
%PY% --version

rem --- 2. create virtual environment
if exist "venv\Scripts\python.exe" (
    echo [2/3] venv already exists, skip creation.
) else (
    echo [2/3] Creating virtual environment venv ...
    %PY% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
)

rem --- 3. install dependencies (Tsinghua PyPI mirror)
echo [3/3] Installing dependencies, may take a few minutes on first run ...
"venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check network and re-run.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup finished!
echo ============================================
echo Next steps:
echo   1. copy start_v2.example.bat  -^>  start_v2.bat
echo   2. edit start_v2.bat, fill in LLM_API_KEY / V2_ADMIN_TOKEN
echo   3. double-click start_v2.bat to start the backend
echo      (default: http://127.0.0.1:5000)
echo.
pause
