@echo off

:: If PG_HOME is set by the user/system, add it to PATH
if defined PG_HOME (
    set "PATH=%PG_HOME%\bin;%PATH%"
)

:: Check if pg_ctl is available
where pg_ctl >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: PostgreSQL tools not found in PATH.
    echo Please add PostgreSQL bin directory to your PATH or set PG_HOME environment variable.
    exit /b 1
)

:: Configuration
set "PG_DATA=%~dp0..\db_data"
set "PG_PORT=5432"
set "PG_LOG=%~dp0db.log"
