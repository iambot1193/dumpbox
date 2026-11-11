# Uso pessoal no PC do dev: sobe o Ollama (se preciso) e o servidor em http://127.0.0.1:8000 com o banco REAL.
# Banco real: $env:DUMPBOX_HOME (padrão D:\dumpbox, com backups diários em D:\dumpbox\backups).
# Desenvolvimento (python run.py, testes) continua usando data/private/, separado.
# Sem senha ainda: abra http://127.0.0.1:8000 no próprio PC e crie pela tela.
$env:DUMPBOX_HOME = if ($env:DUMPBOX_HOME) { $env:DUMPBOX_HOME } else { "D:\dumpbox" }
$env:OLLAMA_MODELS = if ($env:OLLAMA_MODELS) { $env:OLLAMA_MODELS } else { "D:\Ollama\models" }
$ollama = if ($env:OLLAMA_EXE) { $env:OLLAMA_EXE } else { "D:\Ollama\ollama.exe" }
if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) { Start-Process $ollama -ArgumentList serve -WindowStyle Hidden; Start-Sleep 5 }
Write-Host "dumpbox: banco em $env:DUMPBOX_HOME -> http://127.0.0.1:8000"
python -m uvicorn dumpbox.api:app --app-dir "$PSScriptRoot\backend" --host 127.0.0.1 --port 8000
