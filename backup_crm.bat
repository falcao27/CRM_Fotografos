@echo off
setlocal
title Backup - CRM Fotografos

cd /d "%~dp0"

set "BACKUP_ROOT=%USERPROFILE%\Documents\Backups_CRM_Fotografos"
if not exist "%BACKUP_ROOT%" mkdir "%BACKUP_ROOT%"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "DATA_BACKUP=%%I"
set "DESTINO=%BACKUP_ROOT%\Backup_CRM_%DATA_BACKUP%"
mkdir "%DESTINO%"

echo.
echo ==========================================
echo  Backup do CRM Fotografos
echo ==========================================
echo.

if exist "db.sqlite3" (
    copy /Y "db.sqlite3" "%DESTINO%\db.sqlite3" >nul
    echo Banco copiado: db.sqlite3
) else (
    echo AVISO: db.sqlite3 nao encontrado.
)

if exist "media" (
    xcopy "media" "%DESTINO%\media\" /E /I /Y >nul
    echo Pasta copiada: media
) else (
    echo Pasta media nao encontrada. Continuando...
)

echo.
echo Backup criado em:
echo %DESTINO%
echo.
pause
endlocal
