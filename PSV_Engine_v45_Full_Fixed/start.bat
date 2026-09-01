@echo off
setlocal
cd /d %~dp0
set NO_PROXY=192.168.1.26,localhost,127.0.0.1
set no_proxy=%NO_PROXY%

rem Prefer D:\chang\venv, fallback to system python
set PYBIN=python
if exist "%~dp0..\venv\Scripts\python.exe" set PYBIN=%~dp0..\venv\Scripts\python.exe

rem Auto-install langgraph if missing (sequential fallback works without it)
"%PYBIN%" -c "import langgraph" 2>nul
if errorlevel 1 (
  echo [setup] installing langgraph ...
  "%PYBIN%" -m pip install -q langgraph langgraph-checkpoint-sqlite
)

rem Auto-install playwright; skip chromium download if system Chrome exists
rem Detection: 3 standard paths + registry App Paths (covers non-standard installs)
set CHROME_EXE=
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHROME_EXE=1
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHROME_EXE=1
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set CHROME_EXE=1
for /f "skip=2 tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" /ve 2^>nul') do if exist "%%~b" set CHROME_EXE=1
for /f "skip=2 tokens=2*" %%a in ('reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" /ve 2^>nul') do if exist "%%~b" set CHROME_EXE=1
"%PYBIN%" -c "import playwright" 2>nul
if errorlevel 1 (
  echo [setup] installing playwright ...
  "%PYBIN%" -m pip install -q playwright
)
if not defined CHROME_EXE (
  "%PYBIN%" -c "from playwright.sync_api import sync_playwright as s;x=s().start();b=x.chromium.launch();b.close();x.stop()" 2>nul
  if errorlevel 1 (
    echo [setup] no system Chrome found, downloading chromium ...
    "%PYBIN%" -m playwright install chromium
  )
)

rem Desktop browser CDP mode: auto-launch debug browser if port 9222 is not listening
netstat -ano | findstr :9222 | findstr LISTENING >nul
if errorlevel 1 (
  echo [setup] desktop browser not running - launching it now ...
  call "%~dp0start_chrome_debug.bat"
) else (
  echo [ok] desktop browser CDP detected on port 9222 - collection will attach to it.
)

rem Free port 8090 if an old instance is running
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8090 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo PSV v27 Customs Graph Core console: http://localhost:8090
echo Stop: close this window or press Ctrl+C
"%PYBIN%" run_webui.py
