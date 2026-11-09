@echo off
title PisQ Exam Server - GDPT 2018
color 0b
echo =======================================================
echo          PISQ - HE THONG THI TRAC NGHIEM GDPT 2018
echo =======================================================
echo.
if not exist "C:\xampp\xampp_start.exe" (
    echo [LOI] Khong tim thay C:\xampp\xampp_start.exe
    pause
    exit /b 1
)
echo Dang khoi dong XAMPP...
start "XAMPP" "C:\xampp\xampp-control.exe"

echo Dang khoi chay may chu FastAPI...
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON=%~dp0venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)
set "PORT=3000"
start "PisQ API" /D "%~dp0" "%PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 3000 --reload

echo Dang cho may chu san sang...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(60); do { if (Test-NetConnection -ComputerName 127.0.0.1 -Port 3000 -InformationLevel Quiet) { Start-Process 'http://localhost:3000/admin'; exit 0 }; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); Write-Error 'Khong the ket noi may chu tai cong 3000 sau 60 giay.'; exit 1"
if errorlevel 1 echo [LOI] Hay kiem tra cua so PisQ API de xem loi khoi dong.
pause
