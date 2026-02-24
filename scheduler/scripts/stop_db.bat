@echo off
call "%~dp0set_env.bat"

pg_isready -q >nul 2>nul
if %errorlevel% neq 0 (
    echo Database is not running.
    pause
    exit /b 0
)

echo Stopping database server...
pg_ctl -D "%PG_DATA%" stop -m fast
echo Database stopped.
pause
