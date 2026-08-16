@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
set "PORT=18765"

if not exist "%PYTHON%" (
    echo.
    echo [ERROR] Project virtual environment is missing: %PYTHON%
    echo Create .venv and install requirements.txt first.
    pause
    exit /b 1
)

if not exist ".env" (
    echo.
    echo [INFO] .env was not found. Application defaults will be used.
    echo Copy .env.example to .env before enabling local database or external services.
)

echo.
echo [1/2] Applying database migrations...
"%PYTHON%" -m alembic upgrade head
if errorlevel 1 (
    echo.
    echo [ERROR] Database migration failed. The server was not started.
    pause
    exit /b 1
)

echo [2/2] Starting IP Landmark Tourism application...
echo Browser URL: http://127.0.0.1:%PORT%
echo Press Ctrl+C to stop the server.
start "IP Landmark Tourism" http://127.0.0.1:%PORT%
"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload
set "SERVER_EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%SERVER_EXIT_CODE%"=="0" (
    echo [ERROR] The server stopped with exit code %SERVER_EXIT_CODE%.
) else (
    echo [INFO] The server stopped.
)
pause

endlocal
