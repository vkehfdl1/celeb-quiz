@echo off
REM Serves the celeb-quiz repo root via the admin server (static + REST API).
REM Both web/ and data/ are reachable on the same origin; /admin/ exposes the
REM curation UI; /api/* endpoints handle entry mutations.
REM
REM Usage: scripts\serve.bat [port]

setlocal
set PORT=%1
if "%PORT%"=="" set PORT=8765

set ROOT=%~dp0..
cd /d "%ROOT%"

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 scripts\admin_server.py --port %PORT%
    goto :eof
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python scripts\admin_server.py --port %PORT%
    goto :eof
)

echo Error: Python 3 is required (install from https://www.python.org/downloads/) 1>&2
exit /b 1
