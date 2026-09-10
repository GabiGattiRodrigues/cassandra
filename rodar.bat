@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo   ============================================
echo    CASSANDRA - previsao de safras
echo   ============================================
echo.

REM --- acha o Python -----------------------------------------------------
where py >nul 2>&1
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

%PY% --version >nul 2>&1
if errorlevel 1 (
  echo   [X] Python nao encontrado.
  echo       Instale em https://www.python.org/downloads/
  echo       IMPORTANTE: marque "Add Python to PATH" na instalacao.
  echo.
  pause
  exit /b 1
)
for /f "tokens=*" %%v in ('%PY% --version') do echo   Python: %%v

REM --- ambiente virtual (so na primeira vez) -----------------------------
if not exist ".venv\Scripts\python.exe" (
  echo   Criando ambiente virtual ^(so acontece na primeira vez^)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo   [X] Nao consegui criar o ambiente virtual.
    pause
    exit /b 1
  )
  set PRIMEIRA=1
)

set VPY=.venv\Scripts\python.exe

REM --- dependencias ------------------------------------------------------
%VPY% -c "import streamlit, plotly, scipy, pyarrow" >nul 2>&1
if errorlevel 1 (
  echo   Instalando as dependencias... isso leva uns 2 minutos na primeira vez.
  echo.
  %VPY% -m pip install --upgrade pip --quiet
  %VPY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo   [X] Falhou a instalacao das dependencias.
    pause
    exit /b 1
  )
  echo.
)

REM --- confere se os dados pre-calculados estao no lugar ------------------
if not exist "app\dados\painel_safras.parquet" (
  echo   [X] Faltam os arquivos em app\dados\.
  echo       Rode o pipeline antes:
  echo         .venv\Scripts\python prep\00_baixar.py
  echo         .venv\Scripts\python prep\01_load.py
  echo         .venv\Scripts\python prep\02_clean_cohorts.py
  echo         .venv\Scripts\python prep\03_precompute.py
  echo.
  pause
  exit /b 1
)

echo   Subindo o app... o navegador abre sozinho em alguns segundos.
echo   Para parar: feche esta janela ou aperte Ctrl+C.
echo.
%VPY% -m streamlit run app\app.py

echo.
echo   O app foi encerrado.
pause
