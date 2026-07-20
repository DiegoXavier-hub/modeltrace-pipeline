@echo off
setlocal
title ModelTrace - Pipeline NoSQL (apresentacao)
cd /d "%~dp0"

echo ============================================================
echo   ModelTrace - Pipeline NoSQL simplificado (apresentacao)
echo   MongoDB + Redis + Neo4j (GDS) + Streamlit
echo ============================================================
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
docker info >nul 2>&1
if not errorlevel 1 goto dockerok
echo [docker] Docker nao esta ativo - iniciando o Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo [docker] Aguardando o Docker subir (pode levar ~1 min)...
:waitdocker
"%SystemRoot%\System32\timeout.exe" /t 4 >nul
docker info >nul 2>&1
if errorlevel 1 goto waitdocker
:dockerok
echo [docker] Docker ativo.

REM --- 2) Sobe a infra: MongoDB 27018, Redis 6380, Neo4j 7688/7475 ---
echo [infra] Subindo containers (mongo / redis / neo4j)...
docker compose -f docker-compose.pipeline.yml up -d >nul 2>&1
docker start mt-mongo mt-redis mt-neo4j >nul 2>&1

REM --- 3) Espera o Neo4j aceitar conexoes Bolt (porta 7688), ate ~2 min ---
echo [neo4j] Aguardando Bolt em 127.0.0.1:7688...
set /a _tries=0
:waitneo
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',7688);$c.Close();exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 goto neook
set /a _tries+=1
if %_tries% geq 40 (
  echo [neo4j] Aviso: Bolt nao respondeu a tempo - seguindo mesmo assim.
  goto neook
)
"%SystemRoot%\System32\timeout.exe" /t 3 >nul
goto waitneo
:neook
echo [neo4j] Bolt pronto.

REM --- 4) Semeia MongoDB + Redis apenas se o banco estiver vazio ---
"%PY%" -c "import sys;from crud_pipeline import ModelTraceRepository as R;r=R();sys.exit(0 if r.db.predictions.count_documents({})>0 else 1)" >nul 2>&1
if errorlevel 1 (
  echo [seed] Banco vazio - semeando MongoDB + Redis ^(crud_pipeline.py^)...
  "%PY%" crud_pipeline.py
) else (
  echo [seed] MongoDB ja populado - pulando o seed.
)

REM --- 5) Constroi o grafo Neo4j + GDS se ainda nao houver export ---
if not exist "%~dp0logs\graph_export.json" (
  echo [grafo] Gerando grafo Neo4j + GDS ^(graph_pipeline.py^)...
  "%PY%" graph_pipeline.py
) else (
  echo [grafo] graph_export.json ja existe - pulando build.
  echo         ^(Para refazer o grafo: %PY% graph_pipeline.py^)
)

echo.
echo ============================================================
echo   PRONTO! Links do pipeline de apresentacao:
echo ------------------------------------------------------------
echo   Streamlit (interface): http://localhost:8501
echo   Neo4j Browser        : http://localhost:7475
echo      ^(login neo4j / modeltrace123^)
echo   MongoDB : localhost:27018    Redis: localhost:6380
echo ============================================================
echo.
echo   O Streamlit vai abrir no navegador. Aba "Grafo" mostra o
echo   grafo de conhecimento (Neo4j GDS) em 2D/3D.
echo   Feche ESTA janela (ou Ctrl+C) para parar o Streamlit.
echo.

REM --- 6) Libera a porta 8501 (re-execucao) e sobe o Streamlit ---
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" >nul 2>&1
"%STREAMLIT%" run streamlit_app.py --server.port 8501

endlocal