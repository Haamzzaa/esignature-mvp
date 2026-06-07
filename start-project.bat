@echo off
title E-Sign Project Starter
echo ===================================================
echo   E-Sign MVP Development Startup Script
echo ===================================================
echo.

REM Automatically detect script directory (project root)
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

echo Project Root: %PROJECT_ROOT%
echo.

REM ----------------------------------------------------
REM 1. Start Django Backend
REM ----------------------------------------------------
echo [Backend] Checking Django environment...
set "BACKEND_DIR=%PROJECT_ROOT%esign-backend"
set "VENV_DIR=%BACKEND_DIR%\venv"

if not exist "%BACKEND_DIR%" (
    echo [ERROR] Backend folder not found at %BACKEND_DIR%!
    goto error
)

if not exist "%VENV_DIR%" (
    echo [WARNING] Virtual environment not found at %VENV_DIR%!
    echo           Please make sure Python virtual environment is set up.
    echo           Continuing without activating venv...
)

echo [Backend] Spawning backend terminal window...
start "E-Sign Backend (Django)" cmd /k "cd /d "%BACKEND_DIR%" && (if exist "venv\Scripts\activate.bat" (call venv\Scripts\activate.bat) else (echo Warning: Virtual environment not activated.)) && python manage.py runserver"

REM ----------------------------------------------------
REM 2. Start React Frontend
REM ----------------------------------------------------
echo [Frontend] Checking React environment...
set "FRONTEND_DIR=%PROJECT_ROOT%esign-frontend"
set "NODE_MODULES_DIR=%FRONTEND_DIR%\node_modules"

if not exist "%FRONTEND_DIR%" (
    echo [ERROR] Frontend folder not found at %FRONTEND_DIR%!
    goto error
)

if not exist "%NODE_MODULES_DIR%" (
    echo [WARNING] node_modules not found at %NODE_MODULES_DIR%!
    echo           You may need to run 'npm install' in the esign-frontend directory.
)

echo [Frontend] Spawning frontend terminal window...
start "E-Sign Frontend (Vite)" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

echo.
echo ===================================================
echo   Both servers spawned successfully!
echo   You can monitor backend/frontend in their own windows.
echo   To stop, close the spawned windows.
echo ===================================================
pause
exit

:error
echo.
echo [ERROR] Startup failed. Please check paths and verify your setup.
pause
exit
