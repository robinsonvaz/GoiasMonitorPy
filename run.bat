@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
.venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
