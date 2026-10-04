@echo off
cd /d "%~dp0"
python reduktor_masaustu.py
if errorlevel 1 pause
