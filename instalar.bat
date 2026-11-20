@echo off
REM Instalacion rapida en Windows (PC de la U). Requiere internet.
echo Creando entorno virtual...
python -m venv venv
if errorlevel 1 (
    echo No se encontro "python". Probando con "py"...
    py -m venv venv
)
call venv\Scripts\activate.bat
echo Instalando dependencias...
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
echo Corriendo pruebas...
python -m unittest
echo.
echo Listo. Para usar el programa:  venv\Scripts\activate  y luego  python main.py
pause
