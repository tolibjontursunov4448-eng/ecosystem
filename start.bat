@echo off
cd /d "%~dp0"
python -m pip install flask -q
python app.py
pause
