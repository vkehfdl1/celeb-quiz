@echo off
REM Serves the celeb-quiz repo root over HTTP on Windows.
REM Usage: scripts\serve.bat [port]

setlocal
set PORT=%1
if "%PORT%"=="" set PORT=8000

set ROOT=%~dp0..
cd /d "%ROOT%"

echo celeb-quiz local server
echo   Repo root : %ROOT%
echo   Port      : %PORT%
echo   Open      : http://localhost:%PORT%/web/
echo.

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 -m http.server %PORT%
    goto :eof
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python -m http.server %PORT%
    goto :eof
)

echo Error: Python 3 is required (install from https://www.python.org/downloads/) 1>&2
exit /b 1
