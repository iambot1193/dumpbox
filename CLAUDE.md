# dumpbox

Notas soltas → IA cataloga. Servidor no PC (FastAPI+SQLite+Ollama qwen2.5:7b) com PWA em `web/`, acesso via Tailscale; Telegram p/ lembretes (fase 3). App Kotlin foi descartado (opcional no futuro). Detalhes: `docs/arquitetura.md`. Não reler `docs/planejamento.md` salvo necessidade.

## Comandos
- Testes: `python tests/test_rules.py` e `PYTHONUTF8=1 python tests/test_api.py` (API sem Ollama)
- Servidor: `uvicorn dumpbox.api:app --app-dir backend --port 8000` (env: DUMPBOX_PASSWORD_HASH, DUMPBOX_SECRET)
- Avaliar: `python eval/run_eval.py qwen2.5:1.5b` (precisa Ollama: `$env:OLLAMA_MODELS="D:\Ollama\models"; D:\Ollama\ollama.exe serve`)
- Schema: `PYTHONUTF8=1 PYTHONPATH=backend python -m dumpbox.schema > schema/saida_ia.schema.json`

## Regras
- Escritor único: só o celular altera itens; PC devolve propostas.
- Datas e prioridade por regra (`rules.py`), nunca pela IA.
- Repo público: nada em `data/private/`, `.env`, `.gguf`.
- Arquivos pesados em D:, nunca no C:.
- Saída curta: `pytest -q`, `head`, sem despejar logs.
