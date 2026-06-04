@echo off
setlocal
title CRM Fotografos

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: ambiente .venv nao encontrado.
    echo Rode instalar_cliente_windows.bat antes de iniciar o CRM.
    pause
    exit /b 1
)

if not exist "manage.py" (
    echo ERRO: manage.py nao encontrado.
    echo Verifique se este arquivo esta dentro da pasta principal do projeto.
    pause
    exit /b 1
)

start "" "http://127.0.0.1:8000/"
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000

endlocal
