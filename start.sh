#!/usr/bin/env bash
echo "Starting Medanta Hospital - Face Recognition & Threat Security Watchlist Hub on http://localhost:8198..."
cd "$(dirname "$0")/backend"
python3 face_tracker.py
