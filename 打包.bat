@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "UV_CACHE_DIR=%ROOT%.uv-cache"
set "UV_PYTHON_INSTALL_DIR=%ROOT%.uv-python"
set "APP_NAME=EPUB_to_MP3"
set "ICON_DIR=%ROOT%logo"

if not exist "%ICON_DIR%\" (
    echo Missing logo folder: %ICON_DIR%
    echo Create a logo folder next to this bat file and put .ico files in it.
    pause
    exit /b 1
)

set "ICON_COUNT=0"
for %%F in ("%ICON_DIR%\*.ico") do (
    if exist "%%~fF" (
        set /a ICON_COUNT+=1
        set "ICON_!ICON_COUNT!=%%~fF"
        echo !ICON_COUNT!. %%~nxF
    )
)

if "%ICON_COUNT%"=="0" (
    echo No .ico file found in: %ICON_DIR%
    echo Put one .ico file in the logo folder and run this bat again.
    pause
    exit /b 1
)

if "%ICON_COUNT%"=="1" (
    set "ICON_FILE=!ICON_1!"
) else (
    echo.
    set /p ICON_CHOICE=Choose icon number:
    if not defined ICON_%ICON_CHOICE% (
        echo Invalid icon number.
        pause
        exit /b 1
    )
    set "ICON_FILE=!ICON_%ICON_CHOICE%!"
)

echo.
echo Icon: %ICON_FILE%
echo Building...
echo.

uv run --managed-python --with pyinstaller pyinstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onefile ^
    --name "%APP_NAME%" ^
    --icon "%ICON_FILE%" ^
    --collect-all tkinterdnd2 ^
    epub_tts_ui.py

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build done: %ROOT%dist\%APP_NAME%.exe
pause
