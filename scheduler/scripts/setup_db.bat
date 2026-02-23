@echo off
call "%~dp0set_env.bat"

if not exist "%PG_DATA%" (
    echo Initializing database cluster at "%PG_DATA%"...
    mkdir "%PG_DATA%"
    initdb -D "%PG_DATA%" -U postgres -A trust -E UTF8
) else (
    echo Database cluster already exists at "%PG_DATA%".
)

pg_isready -h localhost -p %PG_PORT% >nul 2>nul
if %errorlevel% equ 0 (
    echo Database is already running.
) else (
    echo Starting database server on port %PG_PORT%...
    pg_ctl -D "%PG_DATA%" -o "-p %PG_PORT%" -l "%PG_LOG%" start
    call :wait_for_db
)

echo Setting up user and database...
psql -h localhost -p %PG_PORT% -U postgres -d postgres -c "ALTER USER postgres WITH PASSWORD '123';"
psql -h localhost -p %PG_PORT% -U postgres -lqt | findstr "calendar_db" >nul
if %errorlevel% neq 0 (
    createdb -h localhost -p %PG_PORT% -U postgres calendar_db
) else (
    echo Database calendar_db already exists.
)
psql -h localhost -p %PG_PORT% -U postgres -d calendar_db -f "%~dp0..\sql\init.sql"

echo Setup complete. Database is running on port %PG_PORT%.
echo You can stop it using stop_db.bat
pause
exit /b 0

:wait_for_db
echo Waiting for database to start...
for /L %%i in (1,1,30) do (
    pg_isready -h localhost -p %PG_PORT% >nul 2>nul
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
echo Timed out waiting for database.
exit /b 1
