@echo off
setlocal
title Instalacao - CRM Fotografos

cd /d "%~dp0"

echo.
echo ==========================================
echo  Instalacao do CRM Fotografos
echo ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERRO: Python nao encontrado.
    echo.
    echo Instale o Python 3 e marque a opcao:
    echo Add python.exe to PATH
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERRO: nao foi possivel criar o ambiente virtual.
        pause
        exit /b 1
    )
) else (
    echo Ambiente virtual .venv ja existe.
)

echo.
echo Atualizando pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo AVISO: nao foi possivel atualizar o pip. Continuando instalacao...
)

echo.
echo Instalando dependencias do projeto...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO: falha ao instalar dependencias.
    echo Verifique a internet do computador e tente novamente.
    pause
    exit /b 1
)

echo.
echo Aplicando migrations no banco de dados...
".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 (
    echo.
    echo ERRO: falha ao preparar o banco de dados.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  Usuario administrador
echo ==========================================
echo.
echo Se o usuario admin ainda nao existir, crie agora.
echo Sugestao:
echo Usuario: admin
echo Email: pode deixar vazio
echo Senha: escolha uma senha e guarde
echo.
set /p CRIAR_ADMIN="Deseja abrir a criacao de usuario admin agora? (S/N): "
if /i "%CRIAR_ADMIN%"=="S" (
    ".venv\Scripts\python.exe" manage.py createsuperuser
)

echo.
echo Instalacao concluida.
echo.
echo Proximo passo:
echo Clique duas vezes em criar_atalhos_windows.bat
echo.
pause
endlocal
