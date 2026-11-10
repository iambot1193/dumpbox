# Gera dist\dumpbox.exe (Windows). Uso: .\build.ps1
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --onefile --name dumpbox --paths backend --add-data "web;web" --collect-submodules uvicorn --collect-submodules dumpbox --noconfirm run.py
