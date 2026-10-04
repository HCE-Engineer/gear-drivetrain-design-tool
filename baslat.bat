@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -c "import flask, build123d, scipy" 2>nul
if errorlevel 1 (
    echo Gerekli paketler kuruluyor...
    python -m pip install -r uygulama\requirements.txt
)
python uygulama\app.py
if errorlevel 1 pause
