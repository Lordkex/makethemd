@echo off
setlocal
cd /d "%~dp0"

echo Starting MakeThemd...

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0app.py"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        python "%~dp0app.py"
    ) else (
        echo.
        echo Python nem talalhato a rendszerben.
        echo Telepitsd a Python-t, es engedelyezd az "Add to PATH" opciot.
        echo A projekt README-ben talalod a telepitesi lepeseket.
        pause
        exit /b 1
    )
)

if errorlevel 1 (
    echo.
    echo Az alkalmazas hibaval allt le.
    echo Ha meg nem telepitetted a fuggoosegeket, futtasd:
    echo   py -m pip install -r requirements.txt
    echo   py -m pip install -e "packages\markitdown[all]"
    pause
)
