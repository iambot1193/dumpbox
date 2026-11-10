# Sobe o Ollama (se preciso) e o servidor em http://127.0.0.1:8000
# Antes, uma vez: $env:PYTHONPATH="backend"; python -m dumpbox.setup   (cria a senha)
$env:OLLAMA_MODELS = if ($env:OLLAMA_MODELS) { $env:OLLAMA_MODELS } else { "D:\Ollama\models" }
$ollama = if ($env:OLLAMA_EXE) { $env:OLLAMA_EXE } else { "D:\Ollama\ollama.exe" }
if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) { Start-Process $ollama -ArgumentList serve -WindowStyle Hidden; Start-Sleep 5 }
python -m uvicorn dumpbox.api:app --app-dir "$PSScriptRoot\backend" --host 127.0.0.1 --port 8000
