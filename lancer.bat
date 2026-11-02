@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python fm_live.py
pause
