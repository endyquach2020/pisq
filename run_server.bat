@echo off
title PisQ Exam Server - GDPT 2018
color 0b
echo =======================================================
echo          PISQ - HE THONG THI TRAC NGHIEM GDPT 2018
echo =======================================================
echo.
echo Dang khoi chay may chu FastAPI...
cd /d %~dp0
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
pause
