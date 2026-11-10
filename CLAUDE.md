# dumpbox

Notas soltas → IA cataloga. Servidor no PC (FastAPI+SQLite+Ollama qwen2.5:7b) com PWA em `web/`, acesso via Tailscale; Telegram p/ lembretes (fase 3). App Kotlin foi descartado (opcional no futuro). Detalhes: `docs/arquitetura.md`. Não reler `docs/planejamento.md` salvo necessidade.

## Comandos
- Testes: `python tests/test_rules.py` e `PYTHONUTF8=1 python tests/test_api.py` (API sem Ollama)
- Senha (1x): `PYTHONPATH=backend python -m dumpbox.setup` → `data/private/config.env`. Servidor: `.\iniciar.ps1`
- Exe: `.\build.ps1` → `dist\dumpbox.exe` (PyInstaller; entrada `run.py` → `launcher.py`). 1º uso: tela cria senha (só do PC local) e `ollama_mgr.py` baixa Ollama portátil + modelo por RAM. Release automática: `.github/workflows/release.yml` (tag `v*`).
- Cuidado: caminhos com `\\` passados por heredoc/python -c chegam colapsados; escreva texto com barras invertidas via Write/Edit.
- Chat (`chat.py`): modelo só propõe ações, usuário confirma; nunca gravar direto.
- Avaliar: `python eval/run_eval.py qwen2.5:1.5b` (precisa Ollama: `$env:OLLAMA_MODELS="D:\Ollama\models"; D:\Ollama\ollama.exe serve`)
- Schema: `PYTHONUTF8=1 PYTHONPATH=backend python -m dumpbox.schema > schema/saida_ia.schema.json`

## Regras
- Servidor (SQLite) é a fonte da verdade; navegador só guarda fila offline de capturas.
- Datas e prioridade por regra (`rules.py`), nunca pela IA.
- Repo público: nada em `data/private/`, `.env`, `.gguf`.
- Arquivos pesados em D:, nunca no C:.
- Saída curta: `pytest -q`, `head`, sem despejar logs.
- Testes com o exe: encerrar SÓ pelo PID que iniciei (nunca `Get-Process dumpbox | Stop-Process`): pode matar a instância do usuário.
