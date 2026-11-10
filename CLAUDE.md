# dumpbox

Notas soltas → IA cataloga. Servidor no PC (FastAPI+SQLite+Ollama qwen2.5:7b) com PWA em `web/`, acesso via Tailscale; Telegram p/ lembretes (fase 3). App Kotlin foi descartado (opcional no futuro). Detalhes: `docs/arquitetura.md`. Não reler `docs/planejamento.md` salvo necessidade.

## Comandos
- Testes: `python tests/test_rules.py` e `PYTHONUTF8=1 python tests/test_api.py` (API sem Ollama). Tela: `python tests/ui_browser.py` (Playwright + Chrome; aqui o pacote está em `DUMPBOX_PW_PATH=D:\dev\_mockup_profile\pw`)
- Pastas = tabela `pasta` (slug = `item.contexto`), cache `db.PASTAS`; nunca fixar a lista no código. Enum do JSON Schema montado por chamada.
- Backup do banco real: API de backup do SQLite (cópia simples do .db perde o que está no -wal).
- Senha (1x): `PYTHONPATH=backend python -m dumpbox.setup` → `data/private/config.env`. Servidor: `.\iniciar.ps1`
- Exe: `.\build.ps1` → `dist\dumpbox.exe` (PyInstaller; entrada `run.py` → `launcher.py`). 1º uso: tela cria senha (só do PC local) e `ollama_mgr.py` baixa Ollama portátil + modelo por RAM. Release automática: `.github/workflows/release.yml` (tag `v*`).
- Cuidado: caminhos com `\\` passados por heredoc/python -c chegam colapsados; escreva texto com barras invertidas via Write/Edit.
- Chat (`chat.py`): ações aplicadas na hora, só sobre item citado no pedido, sempre reversíveis (diário `alteracao`). Apagar de vez só pela Lixeira, nunca pela IA.
- Avaliar: `python eval/run_eval.py qwen2.5:1.5b` (precisa Ollama: `$env:OLLAMA_MODELS="D:\Ollama\models"; D:\Ollama\ollama.exe serve`)
- Schema: `PYTHONUTF8=1 PYTHONPATH=backend python -m dumpbox.schema > schema/saida_ia.schema.json`

## Regras
- Servidor (SQLite) é a fonte da verdade; navegador só guarda fila offline de capturas.
- Datas e prioridade por regra (`rules.py`), nunca pela IA.
- Repo público: nada em `data/private/`, `.env`, `.gguf`.
- Arquivos pesados em D:, nunca no C:.
- Saída curta: `pytest -q`, `head`, sem despejar logs.
- Testes com o exe: encerrar SÓ pelo PID que iniciei (nunca `Get-Process dumpbox | Stop-Process`): pode matar a instância do usuário.
- Exe = entregável do cliente: rodar `build.ps1` só em versão final (1.0, 2.0...). No dia a dia use `python run.py`.
