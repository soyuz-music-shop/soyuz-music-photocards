@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -u "SOYUZ_Media_WEB.py" "%~1"
) else (
    python -u "SOYUZ_Media_WEB.py" "%~1"
)
echo.
echo SOYUZ Media WEB stopped. Press any key to close.
pause >nul
