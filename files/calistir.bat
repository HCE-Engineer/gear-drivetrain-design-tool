@echo off
cd /d "%~dp0"
python reduktor.py
if errorlevel 1 pause
