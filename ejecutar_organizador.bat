@echo off
chcp 65001 > nul
title Organizador y Clasificador de Proveedores

echo ======================================================================
echo           ORGANIZADOR Y CLASIFICADOR DE PROVEEDORES
echo ======================================================================
echo.

python "%~dp0organizar_proveedores.py"

echo.
pause
