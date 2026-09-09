@echo off
setlocal

title Codetta Composer
cd /d "%~dp0"

set "CODETTA_COMPOSER_VENV=%~dp0.venv"
set "CODETTA_COMPOSER_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%CODETTA_COMPOSER_PYTHON%" (
    echo.
    echo  Preparing Codetta Composer for first use...
    echo.

    where py.exe >nul 2>nul
    if not errorlevel 1 (
        py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if not errorlevel 1 (
            py -3 -m venv "%CODETTA_COMPOSER_VENV%"
            goto environment_created
        )
    )

    where python.exe >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if not errorlevel 1 (
            python -m venv "%CODETTA_COMPOSER_VENV%"
            goto environment_created
        )
    )

    echo  Python 3.10 or newer was not found.
    echo.
    echo  Install Python from https://www.python.org/downloads/windows/
    echo  Enable "Add Python to PATH" in the installer, then double-click
    echo  this launcher again.
    echo.
    pause
    exit /b 1
)

:environment_created

if not exist "%CODETTA_COMPOSER_PYTHON%" (
    echo.
    echo  The Python environment could not be created.
    echo.
    pause
    exit /b 1
)

"%CODETTA_COMPOSER_PYTHON%" -c "import verovio" >nul 2>nul
if errorlevel 1 (
    echo  Installing Composer dependencies. This is needed only once...
    echo.
    "%CODETTA_COMPOSER_PYTHON%" -m pip install --disable-pip-version-check -r "%~dp0requirements-rendering.txt"
    if errorlevel 1 (
        echo.
        echo  Composer dependencies could not be installed.
        echo  Check your internet connection and try again.
        echo.
        pause
        exit /b 1
    )
    echo.
)

echo.
echo  Starting Codetta Composer...
echo  Your browser will open automatically.
echo  Keep this window open while using Composer.
echo  Close it or press Ctrl+C to stop.
echo.

"%CODETTA_COMPOSER_PYTHON%" -m composer %*

if errorlevel 1 (
    echo.
    echo  Codetta Composer stopped because an error occurred.
    echo.
    pause
)

endlocal
