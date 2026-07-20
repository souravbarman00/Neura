@echo off
rem Set up + start all Neura servers on Windows (cross-platform launcher).
setlocal
set "ROOT=%~dp0.."
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%ROOT%\scripts\neura_serve.py" %*
