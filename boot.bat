@echo off
color 0b
echo ==================================================
echo      CLOUDMETRIX AUTO-BOOTSTRAPPER (SMART FIX)
echo ==================================================

set PYTHON_CMD=
python --version >nul 2>&1
if %errorlevel% equ 0 set PYTHON_CMD=python

if "%PYTHON_CMD%"=="" (
    py --version >nul 2>&1
    if %errorlevel% equ 0 set PYTHON_CMD=py
)

if "%PYTHON_CMD%"=="" (
    python3 --version >nul 2>&1
    if %errorlevel% equ 0 set PYTHON_CMD=python3
)

if "%PYTHON_CMD%"=="" (
    echo ========================================================
    echo [LOI NGIEM TRONG] KHONG TIM THAY PYTHON TREN MAY CUA BAN!
    echo ========================================================
    echo Ban khong the chay du an nay vi thieu phan mem Python.
    echo 1. Hay mo trinh duyet, vao trang: https://www.python.org/downloads/
    echo 2. Tai ban cai dat moi nhat.
    echo 3. KHI CAI DAT, NHO TICH VAO O: "Add Python to PATH" (O duoi cung).
    echo 4. Sau khi cai dat xong, hay chay lai file boot.bat nay.
    echo ========================================================
    pause
    exit /b
)

echo [INFO] Tim thay Python: %PYTHON_CMD%
if not exist "venv" (
    echo [INFO] Dang tao venv...
    %PYTHON_CMD% -m venv venv
)

echo [INFO] Kich hoat moi truong va cai thu vien...
call venv\Scripts\activate.bat
pip install -r requirements.txt
pip install playwright
playwright install chromium

echo [INFO] Booting Server & Worker...
start "CloudMetrix Server" cmd /k "venv\Scripts\python.exe app.py"
start "CloudMetrix Worker" cmd /k "venv\Scripts\huey_consumer.exe workers.huey_app.huey"

echo [SUCCESS] Moi truong da duoc khoi tao!
pause
