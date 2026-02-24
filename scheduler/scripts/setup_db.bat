@echo off
call "%~dp0set_env.bat"

:: 1. Initialize DB cluster
if not exist "%PG_DATA%\PG_VERSION" (
    echo Initializing database cluster at "%PG_DATA%"...
    if not exist "%PG_DATA%" mkdir "%PG_DATA%"
    initdb -D "%PG_DATA%" -U %PGUSER% -A trust -E UTF8
) else (
    echo Database cluster already exists at "%PG_DATA%".
)

:: 2. Start database server
pg_isready -q >nul 2>nul
if %errorlevel% equ 0 (
    echo Database is already running.
) else (
    echo Starting database server on port %PG_PORT%...
    pg_ctl -D "%PG_DATA%" -o "-p %PG_PORT% -k /tmp" -l "%PG_LOG%" start
    call :wait_for_db
)

:: 3. Setup database
echo Setting up database '%PGDATABASE%'...

:: Create database if it doesn't exist
psql -lqt -d postgres | findstr /C:" %PGDATABASE% " >nul
if %errorlevel% neq 0 (
    createdb -U %PGUSER% %PGDATABASE%
) else (
    echo Database '%PGDATABASE%' already exists.
)

:: Initialize tables
psql -d %PGDATABASE% -f "%~dp0..\sql\init.sql"

echo Setup complete. Database is running on port %PG_PORT%.
echo You can stop it using stop_db.bat
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
