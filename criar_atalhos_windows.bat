@echo off
setlocal
title Atalhos - CRM Fotografos

cd /d "%~dp0"

set "PROJECT_DIR=%~dp0"
set "VBS_PATH=%~dp0iniciar_crm_oculto.vbs"
set "DESKTOP_SHORTCUT=%USERPROFILE%\Desktop\CRM Fotografos.lnk"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_SHORTCUT=%STARTUP_DIR%\CRM Fotografos.lnk"

echo.
echo ==========================================
echo  Criacao de atalhos - CRM Fotografos
echo ==========================================
echo.

if not exist "%VBS_PATH%" (
    echo ERRO: iniciar_crm_oculto.vbs nao encontrado.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%DESKTOP_SHORTCUT%'); $s.TargetPath='%VBS_PATH%'; $s.WorkingDirectory='%PROJECT_DIR%'; $s.Description='Abrir CRM Fotografos'; $s.Save()"

if errorlevel 1 (
    echo ERRO: nao foi possivel criar o atalho na Area de Trabalho.
    pause
    exit /b 1
)

echo Atalho criado na Area de Trabalho:
echo %DESKTOP_SHORTCUT%
echo.

set /p INICIAR_WINDOWS="Deseja abrir o CRM automaticamente quando o Windows ligar? (S/N): "
if /i "%INICIAR_WINDOWS%"=="S" (
    if not exist "%STARTUP_DIR%" mkdir "%STARTUP_DIR%"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%STARTUP_SHORTCUT%'); $s.TargetPath='%VBS_PATH%'; $s.WorkingDirectory='%PROJECT_DIR%'; $s.Description='Abrir CRM Fotografos ao iniciar o Windows'; $s.Save()"
    echo.
    echo Atalho criado na inicializacao do Windows.
)

echo.
set /p BACKUP_AUTO="Deseja configurar backup automatico diario as 18:00? (S/N): "
if /i "%BACKUP_AUTO%"=="S" (
    call "%~dp0configurar_backup_automatico.bat"
)

echo.
echo Pronto.
echo O cliente pode abrir o sistema pelo atalho CRM Fotografos.
echo.
pause
endlocal
