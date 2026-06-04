@echo off
setlocal

cd /d "%~dp0"

set "BACKUP_ROOT=%USERPROFILE%\Documents\Backups_CRM_Fotografos"
if not exist "%BACKUP_ROOT%" mkdir "%BACKUP_ROOT%"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "DATA_BACKUP=%%I"
set "DESTINO=%BACKUP_ROOT%\Backup_CRM_%DATA_BACKUP%"
mkdir "%DESTINO%"

if exist "db.sqlite3" copy /Y "db.sqlite3" "%DESTINO%\db.sqlite3" >nul
if exist "media" xcopy "media" "%DESTINO%\media\" /E /I /Y >nul

endlocal
