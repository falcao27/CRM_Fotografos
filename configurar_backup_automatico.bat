@echo off
setlocal
title Backup automatico - CRM Fotografos

cd /d "%~dp0"

set "TASK_NAME=CRM Fotografos Backup Diario"
set "BACKUP_BAT=%~dp0backup_crm_silencioso.bat"

echo.
echo ==========================================
echo  Configurar backup automatico
echo ==========================================
echo.
echo O backup diario sera configurado para 18:00.
echo Os arquivos ficarao em:
echo %USERPROFILE%\Documents\Backups_CRM_Fotografos
echo.

schtasks /Create /SC DAILY /TN "%TASK_NAME%" /TR "cmd.exe /c ""%BACKUP_BAT%""" /ST 18:00 /F
if errorlevel 1 (
    echo.
    echo ERRO: nao foi possivel criar a tarefa de backup automatico.
    echo Tente executar este arquivo como administrador.
    pause
    exit /b 1
)

echo.
echo Backup automatico configurado com sucesso.
echo.
pause
endlocal
