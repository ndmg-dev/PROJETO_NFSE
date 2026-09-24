@echo off
chcp 65001 >nul
title Instalando o sistema NFS-e
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1"
echo.
pause
