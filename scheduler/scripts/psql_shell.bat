@echo off
call "%~dp0set_env.bat"
psql -d %PGDATABASE%
pause
