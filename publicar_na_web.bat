@echo off
setlocal
title ModelTrace - Publicar na web
cd /d "%~dp0"

echo ============================================================
echo   ModelTrace - Ligar o servidor e publicar na internet
echo ============================================================
echo.
echo   Este script deixa o PC como servidor deste projeto:
echo   sobe os bancos, o Streamlit e um link publico (Cloudflare
echo   Tunnel). Os bancos NAO ficam expostos - so o Streamlit
echo   atravessa o tunel, os bancos continuam so em localhost.
echo.

REM --- 0) Usa o ambiente virtual criado por instalar.bat, se existir ---
set "PY=python"
set "STREAMLIT=streamlit"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
  set "STREAMLIT=.venv\Scripts\streamlit.exe"
) else (
  echo [aviso] .venv nao encontrado - usando o Python global.
  echo         Recomendado: rode instalar.bat primeiro.
  echo.
)

REM --- 1) Garante que o Docker Desktop esta rodando ---
echo [1/6] Verificando Docker...
docker info >nul 2>&1
if not errorlevel 1 goto dockerok
echo       Docker nao esta ativo - iniciando o Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo       Aguardando o Docker subir (pode levar ~1 min)...
:waitdocker
"%SystemRoot%\System32\timeout.exe" /t 4 >nul
docker info >nul 2>&1
if errorlevel 1 goto waitdocker
:dockerok
echo       Docker ativo.

REM --- 2) Sobe a infra: MongoDB 27018, Redis 6380, Neo4j 7688/7475 ---
echo.
echo [2/6] Subindo containers (mongo / redis / neo4j)...
docker compose -f docker-compose.pipeline.yml up -d >nul 2>&1
docker start mt-mongo mt-redis mt-neo4j >nul 2>&1

REM --- 3) Espera o Neo4j aceitar conexoes Bolt, ate ~2 min ---
echo       Aguardando Neo4j em 127.0.0.1:7688...
set /a _tries=0
:waitneo
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',7688);$c.Close();exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 goto neook
set /a _tries+=1
if %_tries% geq 40 (
  echo       Aviso: Neo4j nao respondeu a tempo - seguindo mesmo assim.
  goto neook
)
"%SystemRoot%\System32\timeout.exe" /t 3 >nul
goto waitneo
:neook
echo       Bancos prontos.

REM --- 4) Semeia MongoDB + Redis apenas se o banco estiver vazio ---
echo.
echo [3/6] Conferindo dados...
"%PY%" -c "import sys;from crud_pipeline import ModelTraceRepository as R;r=R();sys.exit(0 if r.db.predictions.count_documents({})>0 else 1)" >nul 2>&1
if errorlevel 1 (
  echo       Banco vazio - semeando MongoDB + Redis...
  "%PY%" crud_pipeline.py
) else (
  echo       MongoDB ja populado.
)

REM --- 5) Constroi o grafo Neo4j + GDS se ainda nao houver export ---
if not exist "%~dp0logs\graph_export.json" (
  echo       Gerando grafo Neo4j + GDS...
  "%PY%" graph_pipeline.py
) else (
  echo       Grafo ja existe.
)

REM --- 6) Sobe o Streamlit numa janela propria (nao trava este script) ---
echo.
echo [4/6] Iniciando o Streamlit numa janela separada...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" >nul 2>&1
start "ModelTrace - App (local)" cmd /k ""%PY%" -m streamlit run streamlit_app.py --server.port 8501 --server.headless true"

echo       Aguardando o Streamlit responder em localhost:8501...
set /a _tries=0
:waitst
powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri 'http://127.0.0.1:8501' -UseBasicParsing -TimeoutSec 2)|Out-Null;exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 goto stok
set /a _tries+=1
if %_tries% geq 30 (
  echo       Aviso: Streamlit demorou a responder - seguindo mesmo assim.
  goto stok
)
"%SystemRoot%\System32\timeout.exe" /t 2 >nul
goto waitst
:stok
echo       Streamlit no ar.

REM --- 7) Confere/baixa o cloudflared (fica local ao projeto, sem precisar de admin) ---
echo.
echo [5/6] Preparando o link publico (Cloudflare Tunnel)...
set "CLOUDFLARED=cloudflared.exe"
if exist "cloudflared.exe" goto cfok
where cloudflared >nul 2>&1
if not errorlevel 1 (
  set "CLOUDFLARED=cloudflared"
  goto cfok
)
echo       cloudflared nao encontrado - baixando (~55 MB, so na 1a vez)...
powershell -NoProfile -Command "try{Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe' -UseBasicParsing;exit 0}catch{exit 1}"
if errorlevel 1 (
  echo       [ERRO] Nao foi possivel baixar o cloudflared automaticamente.
  echo              Baixe manualmente em https://github.com/cloudflare/cloudflared/releases
  echo              e salve como "cloudflared.exe" nesta pasta.
  goto fim
)
:cfok

REM Caminho absoluto: PowerShell nao executa arquivo do diretorio atual sem
REM prefixo ".\", entao resolvemos o caminho completo aqui pra funcionar nos
REM dois casos (copia local em cloudflared.exe ou instalado no PATH).
if exist "%~dp0cloudflared.exe" (
  set "CLOUDFLARED_FULL=%~dp0cloudflared.exe"
) else (
  for /f "usebackq delims=" %%p in (`where cloudflared`) do set "CLOUDFLARED_FULL=%%p"
)

echo.
echo [6/6] Abrindo o tunel publico numa janela separada...
del /q "%~dp0cloudflared_tunnel.log" >nul 2>&1
start "ModelTrace - Link publico (Cloudflare Tunnel)" powershell -NoExit -NoProfile -Command ^
  "& '%CLOUDFLARED_FULL%' tunnel --url http://localhost:8501 2>&1 | Tee-Object -FilePath '%~dp0cloudflared_tunnel.log'"

echo       Aguardando o link publico ser criado...
set "PUBLIC_URL="
for /f "usebackq delims=" %%u in (`powershell -NoProfile -File "%~dp0aguardar_tunel.ps1" -LogPath "%~dp0cloudflared_tunnel.log"`) do set "PUBLIC_URL=%%u"

echo.
echo ============================================================
echo   PRONTO! O servidor esta no ar.
echo ------------------------------------------------------------
if not "%PUBLIC_URL%"=="" (
  echo   Link publico ^(compartilhe este^):
  echo     %PUBLIC_URL%
) else (
  echo   Aviso: nao consegui confirmar o link ainda.
  echo   Olhe a janela "Link publico" ou o arquivo cloudflared_tunnel.log
  echo   e procure uma linha terminando em .trycloudflare.com
)
echo.
echo   O link muda toda vez que este script roda. Se quiser um
echo   endereco fixo, isso exige um dominio proprio no Cloudflare
echo   (ver README.md, secao "Publicar na web").
echo.
echo   Local (so nesta rede): http://localhost:8501
echo   Neo4j Browser        : http://localhost:7475  (neo4j / modeltrace123)
echo.
echo   Para PARAR tudo: feche as 2 janelas abertas e rode
echo   "docker compose -f docker-compose.pipeline.yml stop".
echo ============================================================
echo.

:fim
pause
endlocal
