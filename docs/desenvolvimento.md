# Guia de desenvolvimento

Decisões e modelo de dados ficam em [`arquitetura.md`](arquitetura.md); a API em [`api.md`](api.md). Aqui: como rodar, testar, mudar e publicar.

## Requisitos

- Python 3.11 (`pip install -r requirements.txt`)
- [Ollama](https://ollama.com) com `qwen2.5:7b` (ou `qwen2.5:1.5b` em PC com menos de 16 GB de RAM). `python run.py` baixa e sobe sozinho se não achar.
- Opcional: Playwright + Chrome para o teste de tela.

## Rodar

```bash
python run.py                                   # servidor + navegador + preparo automático do Ollama
python -m uvicorn dumpbox.api:app --app-dir backend --reload   # só o servidor, Ollama já rodando
```

No Windows, `iniciar.ps1` sobe Ollama e servidor com o **banco de uso real** (`DUMPBOX_HOME`, padrão `D:\dumpbox`); `python run.py` usa `data/private/` (dev). Ajuste `OLLAMA_EXE`/`OLLAMA_MODELS` se preciso.

Senha: crie pela tela no primeiro acesso, ou pelo terminal com `PYTHONPATH=backend python -m dumpbox.setup`. Fica só o hash em `data/private/config.env`.

## Fluxo de uma nota

```
PWA (fila em localStorage, UUID)
  └─ POST /api/capturas ──> captura(status=pendente)
                               └─ worker (thread em api.py, 1 por vez)
                                    ├─ editor.parece_comando? ──> editor.interpretar (ações + itens novos)
                                    └─ senão ──> classifier.classificar (Ollama + JSON Schema)
                                                   └─ rules.py (prazo, prioridade) ──> db.salvar_resultado
```

| Arquivo | Papel |
|---|---|
| `api.py` | rotas, login, worker em segundo plano |
| `classifier.py` | prompt, chamada ao Ollama com `format` = JSON Schema, versões de prompt (`DUMPBOX_PROMPT`) |
| `visao.py` | foto de lista: modelo de visão transcreve (`item => marcada/vazia`), classificador cataloga |
| `editor.py` | detecta instruções (regex + fuzzy), uma chamada por instrução, reorganização em massa |
| `chat.py` | ações validadas (`validar`/`aplicar`), diário `alteracao`, `desfazer`, chat |
| `rules.py` | datas em pt-BR e prioridade, sem IA |
| `db.py` | SQLite (WAL), migrações, pastas (cache `db.PASTAS`), exemplos aprendidos, lixeira |
| `schema.py` | contrato Pydantic da saída da IA |
| `ollama_mgr.py` | acha/baixa Ollama portátil, escolhe modelo pela RAM, progresso em `ESTADO` |
| `auth.py`, `setup.py` | hash scrypt, token HMAC, limite de tentativas, criação de senha |
| `config.py` | pasta de dados e leitura de `config.env` |
| `launcher.py` | entrada do exe: porta livre, abre o navegador |
| `web/` | PWA sem build: `index.html`, `app.js`, `sw.js` |

## Variáveis de ambiente

Lidas do ambiente ou de `config.env` (o ambiente tem prioridade). Modelo em [`.env.example`](../.env.example).

| Variável | Padrão | Uso |
|---|---|---|
| `DUMPBOX_HOME` | `data/private/` (dev), `%LOCALAPPDATA%\dumpbox` (exe) | pasta de dados |
| `DUMPBOX_CONFIG` | `$DUMPBOX_HOME/config.env` | arquivo de config |
| `DUMPBOX_DB` | `$DUMPBOX_HOME/dumpbox.db` | banco SQLite |
| `DUMPBOX_PASSWORD_HASH` | | hash da senha (criado pelo setup) |
| `DUMPBOX_SECRET` | aleatório a cada início | assina o cookie; fixe para não perder a sessão ao reiniciar |
| `DUMPBOX_COOKIE_SECURE` | `0` | `1` quando servir por HTTPS |
| `DUMPBOX_MODEL` | pela RAM | força o modelo do Ollama |
| `DUMPBOX_PROMPT` | `v2` | versão do prompt do classificador |
| `DUMPBOX_MODELO_VISAO` | `qwen2.5vl:3b` | modelo de visão (foto de lista); o exe baixa depois do de texto |
| `DUMPBOX_WORKER` | `1` | `0` desliga o worker (testes) |
| `DUMPBOX_AUTOPREPARO` | `1` no `run.py`/exe | baixa e sobe o Ollama sozinho |
| `DUMPBOX_NO_BROWSER` | | `1` não abre o navegador |
| `OLLAMA_URL` | `http://localhost:11434` | endereço do Ollama |

## Testes

```bash
python tests/test_rules.py                    # datas e prioridade
PYTHONUTF8=1 python tests/test_api.py         # API, editor, chat, pastas, lixeira; Ollama trocado por um falso
python tests/ui_browser.py                    # tela real no Chrome headless, PC e celular, banco temporário
```

`ui_browser.py` precisa de Playwright; se ele estiver fora do ambiente, aponte com `DUMPBOX_PW_PATH`. Todos usam banco temporário: não tocam no seu.

## Avaliar o modelo

```bash
python eval/run_eval.py qwen2.5:7b                                # 46 casos sintéticos em data/public/casos.jsonl
python eval/run_eval.py qwen2.5:7b data/private/casos.jsonl       # suas notas reais (fora do git)
```

```bash
python eval/gera_imagens.py                                       # 24 checklists sintéticos + gabarito
python eval/run_eval_visao.py qwen2.5vl:3b -v                     # itens achados, marcado certo por estilo
```

Mede JSON válido, nº de itens, tipo, contexto, prazo e latência p50. Ao mudar o prompt, crie uma versão nova em `classifier.py`, rode o eval com `DUMPBOX_PROMPT` e atualize a tabela do README.

## Mudanças comuns

- **Saída da IA:** edite `schema.py` e regenere o arquivo de referência:
  `PYTHONUTF8=1 PYTHONPATH=backend python -m dumpbox.schema > schema/saida_ia.schema.json`
- **Pastas:** vêm da tabela `pasta` (cache `db.PASTAS`). Nunca fixe a lista no código; o enum do JSON Schema é montado a cada chamada.
- **Datas e prioridade:** só em `rules.py`, nunca pedir ao modelo. Cubra o caso em `tests/test_rules.py`.
- **Nova ação da IA:** adicione em `chat.Acao`, `_COLUNA` (whitelist de coluna) e `validar`. Toda ação precisa passar pelo diário para ter Desfazer; apagar de vez nunca é ação da IA.
- **PWA:** ao mudar arquivos do casco, suba a versão `V` em `web/sw.js` para o celular pegar a nova.

## Backup do banco

O worker faz um backup por dia em `<pasta do banco>/backups/dumpbox-AAAA-MM-DD.db` e guarda os 14 mais novos (`db.backup_diario`). Para restaurar, pare o servidor e copie um deles por cima de `dumpbox.db` (apague `-wal`/`-shm`).

Backup manual: o banco usa WAL; copiar só o `.db` perde o que está no `-wal`. Use a API de backup do SQLite:

```bash
python -c "import sqlite3; s=sqlite3.connect('data/private/dumpbox.db'); d=sqlite3.connect('backup.db'); s.backup(d)"
```

## Publicar uma versão

- No dia a dia rode com `python run.py`; o exe é o entregável e só é gerado em versão final.
- Local: `.\build.ps1` gera `dist\dumpbox.exe` (PyInstaller, venv em `.venv`).
- CI: `git tag v1.0 && git push --tags` dispara `.github/workflows/release.yml`, que roda os testes, gera o exe e anexa à release.

## Regras do repositório

- Repo público: nada de `data/private/`, `.env`, `.db`, `.gguf` (já no `.gitignore`). Testes e mockups usam dados inventados.
- O servidor (SQLite) é a fonte da verdade; o navegador só guarda a fila de capturas offline.
- Texto de nota é dado não confiável: ações da IA são de conjunto fechado e validadas no servidor.
