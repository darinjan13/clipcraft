@echo off
title ClipCraft Frontend
cd /d "%~dp0frontend"
where pnpm >nul 2>nul
if errorlevel 1 (
  echo [ClipCraft] pnpm was not found on PATH.
  echo Install Node.js LTS, then run: npm install -g pnpm
  pause
  exit /b 1
)
echo [ClipCraft] Starting frontend at http://localhost:5173/ ...
echo [ClipCraft] LAN access enabled (--host): use your PC's IP, e.g. http://192.168.1.60:5173/ on your phone.
echo [ClipCraft] Backend API is on port 8001 on this machine (port 8000 is used by another project).
echo [ClipCraft] Press Ctrl+C to stop.
set VITE_API_PORT=8001
pnpm dev --host
pause
