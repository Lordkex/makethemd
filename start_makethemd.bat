@echo off
setlocal
cd /d "%~dp0"

echo Starting MakeThemd...

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "SETUP_PY="

"%VENV_PY%" -c "" >nul 2>nul
if not errorlevel 1 (
    set SETUP_PY="%VENV_PY%"
    goto :setup
)

rem First start on this machine: PaddlePaddle has no wheels for Python 3.14 or newer.
for %%v in (3.12 3.13 3.11 3.10) do (
    py -%%v -c "" >nul 2>nul
    if not errorlevel 1 (
        set "SETUP_PY=py -%%v"
        goto :setup
    )
)
python -c "" >nul 2>nul
if not errorlevel 1 (
    set "SETUP_PY=python"
    goto :setup
)

echo.
echo Python was not found on this system.
echo Install Python 3.12 and enable the "Add to PATH" option.
echo See the README for the installation steps.
pause
exit /b 1

:setup
rem Creates .venv on the first start and picks the GPU or CPU engines for this machine.
%SETUP_PY% "%~dp0setup_env.py"
if errorlevel 1 goto :failed

rem weekly update of the downloader packages; the app starts even if it fails
"%VENV_PY%" "%~dp0updater.py"
"%VENV_PY%" "%~dp0app.py"
if not errorlevel 1 exit /b 0
echo.
echo The app stopped with an error.
pause
exit /b 1

:failed
echo.
echo The project environment could not be set up. See the message above.
pause
exit /b 1
