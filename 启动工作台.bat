@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Futures Cost Terminal v0.5.1 - CNEquity Futures
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating Python virtual environment ...
  py -3 -m venv .venv
  if errorlevel 1 (echo Python unavailable. Install Python 3.11 or 3.12. & pause & exit /b 1)
)
if not exist ".venv\.deps_ready_v05" (
 echo [2/3] Installing free CNEquity and other dependencies. Internet required the first time.
 call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
 if errorlevel 1 (echo [ERROR] Dependency installation failed. See lines above. & pause & exit /b 1)
 type nul > ".venv\.deps_ready_v05"
) else (
 echo [2/3] Dependencies already installed: skipping slow pip install.
)
echo [3/3] Browser: http://127.0.0.1:8501
REM Streamlit opens exactly one browser tab. Do not launch an extra PowerShell browser.
call ".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 echo [ERROR] Failed to start app. Close older workbench on port 8501, then try again.
pause
