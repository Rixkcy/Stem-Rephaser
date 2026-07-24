@echo off
title Stem Rephaser ^& Media Sanitizer Suite
echo ===================================================
echo   STEM REPHASER ^& MEDIA SANITIZER SUITE
echo ===================================================
echo.
echo Launching web interface...
start "" "http://127.0.0.1:5000"
echo Starting Flask backend server...
if exist venv\Scripts\python.exe (
    echo [OK] Using virtual environment python.
    venv\Scripts\python.exe app.py
) else (
    echo [!] Using global python.
    python app.py
)
