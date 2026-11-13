@echo off
title Medanta Hospital - Face Recognition & Threat Security Watchlist Hub
echo ======================================================================
echo   Medanta Hospital - Face Recognition & Threat Security Watchlist Hub
echo   Opening at: http://localhost:8198
echo ======================================================================
cd /d "%~dp0backend"
python face_tracker.py
pause
