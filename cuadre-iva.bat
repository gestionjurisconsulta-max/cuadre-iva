@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo No se encuentra Python en el PATH.
  echo Instalalo desde https://www.python.org/downloads/ marcando "Add python.exe to PATH".
  pause
  exit /b 1
)

python -c "import streamlit, pandas, openpyxl, jinja2" >nul 2>&1
if errorlevel 1 (
  echo Faltan librerias. Instalando...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo No se han podido instalar las librerias.
    pause
    exit /b 1
  )
)

echo.
echo   Cuadre de IVA A3 . Bilky
echo   Se abrira en el navegador. Para cerrar, cierra esta ventana.
echo.
python -m streamlit run app.py --server.address=localhost
pause
