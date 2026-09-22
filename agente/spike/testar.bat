@echo off
chcp 65001 >nul
title Teste de certificado - spike do agente NFS-e
cd /d "%~dp0"

where java >nul 2>nul
if errorlevel 1 (
    echo.
    echo O Java nao foi encontrado nesta maquina.
    echo.
    echo Instale o JDK 21 (Temurin) antes de continuar:
    echo   https://adoptium.net/temurin/releases/?version=21
    echo.
    echo Na instalacao, marque a opcao "Add to PATH".
    echo Depois de instalar, feche esta janela e clique de novo em testar.bat.
    echo.
    pause
    exit /b 1
)

echo Compilando...
javac *.java
if errorlevel 1 (
    echo.
    echo A compilacao falhou. Copie o texto acima e envie para quem preparou este teste.
    echo.
    pause
    exit /b 1
)

echo Abrindo a janela do teste...
start "" java ProvarHandshakeMTLSGui
