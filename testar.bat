@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo   ============================================
echo    CASSANDRA - testes
echo   ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo   [X] Ambiente virtual nao existe. Rode o rodar.bat primeiro.
  pause
  exit /b 1
)
set VPY=.venv\Scripts\python.exe

echo   [1/3] Recuperacao de parametros do BG/NBD e do Gamma-Gamma
echo   ------------------------------------------------------------
%VPY% tests\test_btyd.py
if errorlevel 1 goto falhou

echo.
echo   [2/3] Graficos e conferencia das pilhas
echo   ------------------------------------------------------------
%VPY% tests\test_graficos.py
if errorlevel 1 goto falhou

echo.
echo   [3/3] Reconciliacao com a base bruta
echo   ------------------------------------------------------------
if not exist "data\transacoes.parquet" (
  echo   pulado: precisa rodar o pipeline em prep\ para ter data\transacoes.parquet
) else (
  %VPY% tests\test_reconciliacao.py
  if errorlevel 1 goto falhou
)

echo.
echo   ============================================
echo    TUDO PASSOU
echo   ============================================
pause
exit /b 0

:falhou
echo.
echo   ============================================
echo    ALGUM TESTE FALHOU - veja a mensagem acima
echo   ============================================
pause
exit /b 1
