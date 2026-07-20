@echo off
rem Neura CLI launcher for Windows. Runs in the current folder (that becomes the workspace).
setlocal
set "ROOT=%~dp0.."
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%ROOT%\cli\neura.py" %*
