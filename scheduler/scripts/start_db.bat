@echo off
call "%~dp0set_env.bat"

pg_isready -q >nul 2>nul
if %errorlevel% equ 0 (
    echo Database is already running on port %PG_PORT%.
    pause
    exit /b 0
)

echo Starting database server on port %PG_PORT%...
pg_ctl -D "%PG_DATA%" -o "-p %PG_PORT% -k /tmp" -l "%PG_LOG%" start
call :wait_for_db
echo Database started. Logs: %PG_LOG%
pause
exit /b 0

:wait_for_db
echo Waiting for database to start...
for /L %%i in (1,1,30) do (
    pg_isready -q >nul 2>nul
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
echo Timed out waiting for database.
exit /b 1
