@echo off
setlocal
cd /d %~dp0

rem Start a REAL desktop browser with CDP debug port, so PSV can attach to it.
rem Cloudflare sees a genuine desktop browser with persistent profile/cookies.
rem NOTE: Chrome 136+ ignores the debug port on the DEFAULT profile, so we use
rem a dedicated profile folder: chrome_profile (cookies persist across runs).

set PROFILE=%~dp0chrome_profile
set EXE=

rem Prefer Google Chrome: standard paths + registry
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set EXE=%LocalAppData%\Google\Chrome\Application\chrome.exe
for /f "skip=2 tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" /ve 2^>nul') do if not defined EXE set EXE=%%~b
for /f "skip=2 tokens=2*" %%a in ('reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" /ve 2^>nul') do if not defined EXE set EXE=%%~b

rem Fallback: Microsoft Edge (also Chromium, CDP compatible)
if not defined EXE if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe
if not defined EXE if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe
for /f "skip=2 tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" /ve 2^>nul') do if not defined EXE set EXE=%%~b

if not defined EXE (
  echo [X] No Chrome or Edge found on this machine.
  pause
  exit /b 1
)

echo Starting desktop browser with CDP on port 9222 ...
echo   exe     = %EXE%
echo   profile = %PROFILE%
echo.
echo FIRST TIME ONLY: if a "verify you are human" checkbox appears on the
echo ImportYeti page, click it once. The cookie is saved in the profile and
echo you will not be asked again.
echo.
echo Leave this browser OPEN while PSV is collecting.
start "" "%EXE%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check "https://www.importyeti.com/search?q=birthday+candles"
echo Browser started. You can close THIS black window now (keep the browser open).
timeout /t 5 >nul
