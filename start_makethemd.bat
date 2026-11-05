@echo off
setlocal
cd /d "%~dp0"

echo Starting MakeThemd...

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0updater.py"
    "%~dp0.venv\Scripts\python.exe" "%~dp0app.py"
    goto :check_result
)

where py >nul 2>nul
if not errorlevel 1 (
    rem weekly update of the downloader packages; the app starts even if it fails
    py -3 "%~dp0updater.py"
    py -3 "%~dp0app.py"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        python "%~dp0updater.py"
        python "%~dp0app.py"
    ) else (
        echo.
        echo Python was not found on this system.
        echo Install Python and enable the "Add to PATH" option.
        echo See the README for the installation steps.
        pause
        exit /b 1
    )
)

:check_result
if errorlevel 1 (
    echo.
    echo The app stopped with an error.
    echo If you have not installed the dependencies yet, run:
    echo   py -m pip install -r requirements.txt
    echo   py -m pip install -e "packages\markitdown[all]"
    pause
)
