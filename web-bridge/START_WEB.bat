@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "SOYUZ_Media_WEB.py"
) else (
    python "SOYUZ_Media_WEB.py"
)
echo.
echo SOYUZ Media WEB stopped. Press any key to close.
pause >nul
