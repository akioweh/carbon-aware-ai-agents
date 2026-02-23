@echo off
call "%~dp0set_env.bat"
psql -h localhost -p %PG_PORT% -U postgres -d calendar_db
pause
