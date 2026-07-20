@echo off
setlocal
title ModelTrace - Instalar dependencias e verificar ambiente
cd /d "%~dp0"

echo ============================================================
echo   ModelTrace - Instalacao e verificacao do ambiente
echo ============================================================
echo.

set FALTOU=0

REM --- aviso se o caminho do projeto for muito longo (limite do Windows) ---
for /f %%L in ('powershell -NoProfile -Command "('%~dp0').Length"') do set PATHLEN=%%L
if %PATHLEN% GTR 150 (
  echo [aviso] O caminho deste projeto tem %PATHLEN% caracteres. Caminhos muito
  echo         longos podem causar erros obscuros de DLL no Windows ^(ex.: pyarrow^).
  echo         Se algo falhar mais abaixo, mova a pasta para um caminho mais curto.
  echo.
)

REM --- 1) Python ---
echo [1/6] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo   [FALTA] Python nao encontrado no PATH.
  echo           Instale em https://www.python.org/downloads/ e marque a opcao
  echo           "Add python.exe to PATH" durante a instalacao.
  set FALTOU=1
  goto resumo
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   [OK] %%v

REM --- 2) Docker ---
echo.
echo [2/6] Verificando Docker...
docker --version >nul 2>&1
if errorlevel 1 (
  echo   [FALTA] Docker nao encontrado no PATH.
  echo           Instale o Docker Desktop em https://www.docker.com/products/docker-desktop/
  set FALTOU=1
) else (
  for /f "tokens=*" %%v in ('docker --version') do echo   [OK] %%v
  docker info >nul 2>&1
  if errorlevel 1 (
    echo   [aviso] Docker instalado, mas o Docker Desktop nao esta aberto agora.
    echo           Abra o Docker Desktop antes de rodar executar_pipeline.bat.
  ) else (
    echo   [OK] Docker Desktop esta rodando.
  )
)

REM --- 3) Git (a biblioteca do grafo instala direto do GitHub) ---
echo.
echo [3/6] Verificando Git...
git --version >nul 2>&1
if errorlevel 1 (
  echo   [FALTA] Git nao encontrado no PATH ^(necessario para instalar a
  echo           biblioteca constelario, que vem direto do GitHub^).
  echo           Instale em https://git-scm.com/downloads
  set FALTOU=1
) else (
  for /f "tokens=*" %%v in ('git --version') do echo   [OK] %%v
)

REM --- 4) Ambiente virtual Python isolado deste projeto ---
echo.
echo [4/6] Preparando ambiente virtual (.venv)...
if exist ".venv\Scripts\python.exe" (
  echo   [OK] .venv ja existe.
) else (
  python -m venv .venv
  if errorlevel 1 (
    echo   [ERRO] Falha ao criar o ambiente virtual.
    set FALTOU=1
    goto resumo
  )
  echo   [OK] .venv criado.
)

REM --- 5) Instala as dependencias dentro do .venv ---
echo.
echo [5/6] Instalando dependencias ^(a 1a vez pode levar alguns minutos^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements-pipeline.txt
if errorlevel 1 (
  echo   [ERRO] Falha ao instalar dependencias - veja o log acima.
  set FALTOU=1
  goto resumo
)
echo   [OK] Dependencias instaladas.

REM --- 6) Confere se cada biblioteca importa corretamente ---
echo.
echo [6/6] Verificando bibliotecas Python instaladas...
".venv\Scripts\python.exe" verificar_ambiente.py
if errorlevel 1 set FALTOU=1

:resumo
echo.
echo ============================================================
if "%FALTOU%"=="0" (
  echo   Tudo certo! Para rodar o projeto:
  echo.
  echo     executar_pipeline.bat
) else (
  echo   Alguma coisa acima precisa de atencao - leia as linhas
  echo   [FALTA]/[ERRO], resolva e rode este instalar.bat de novo.
)
echo ============================================================
echo.
pause
endlocal
