@echo off
setlocal

cd /d "%~dp0"

if not exist .venv (
    echo Criando ambiente virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo ERRO: nao consegui criar o ambiente virtual. O Python esta instalado e no PATH?
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo Instalando dependencias (so na primeira vez)...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERRO: falha ao instalar dependencias.
    pause
    exit /b 1
)

set /p PFX="Caminho do arquivo .pfx do certificado: "
if not exist "%PFX%" (
    echo ERRO: nao encontrei o arquivo "%PFX%"
    pause
    exit /b 1
)

python fase0_dfe.py --ambiente restrita --pfx "%PFX%" --dump-contrato

echo.
echo Resultado tambem salvo em poc\out\contrato\ — copie a saida acima e mande de volta.
pause
