# Arquitetura e decisões

## DECISÃO ATUAL (10/11/2026): PWA hospedada no PC + Tailscale
Substitui o app Kotlin (as seções abaixo sobre Android ficam como histórico/opcional).
- **Servidor no PC** (FastAPI + SQLite + worker + Ollama `qwen2.5:7b`) é a fonte da verdade. Acaba o sync entre dois bancos.
- **PWA** (`web/`): instala no celular, fila de capturas offline no navegador (localStorage + UUID → envio idempotente quando o servidor voltar).
- **Acesso:** Tailscale (`tailscale serve`, URL privada HTTPS só nos seus aparelhos). Nada de port-forward. Cloudflare Tunnel + Access fica como opção futura.
- **Login próprio** (NÃO a senha do Windows): scrypt, cookie `HttpOnly` + `SameSite=Strict`, 5 tentativas/min/IP. Com HTTPS ligar `DUMPBOX_COOKIE_SECURE=1`.
- **Lembretes** via bot Telegram do PC (fase 3). Sem PC ligado, sem lembrete: trade-off aceito.
- **Portfólio:** link clicável + modo demo com dados sintéticos (pendente); instância real fica privada.

### Rodar
```powershell
$env:PYTHONPATH = "backend"; python -m dumpbox.setup     # 1x: cria a senha (grava só o hash em data/private/config.env)
.\iniciar.ps1                                            # sobe Ollama + servidor em http://127.0.0.1:8000
tailscale serve --bg 8000                                # depois de instalar o Tailscale: URL HTTPS privada
```

### Distribuição: um exe para PC virgem
- `dumpbox.exe` (PyInstaller, ~14 MB, sem Python) sobe o servidor em 127.0.0.1 e abre o navegador. Dados em `%LOCALAPPDATA%/dumpbox`.
- **Assistente de primeiro uso:** sem senha configurada, a tela pede para criar uma. `POST /api/setup` só vale **sem senha existente** e **do próprio PC** (host loopback e nenhum cabeçalho de proxy/túnel), para ninguém assumir o app via Tailscale/Cloudflare.
- **`ollama_mgr.py`:** usa o Ollama se já estiver rodando; senão acha/baixa o zip portátil (1,6 GB), sobe em segundo plano e puxa o modelo (7B com ≥16 GB de RAM, senão 1.5B). Progresso em `GET /api/estado`; até ficar pronto, o worker deixa as notas `pendentes`.
- Build local `build.ps1`; CI em `.github/workflows/release.yml` roda os testes, gera o exe e anexa à release de tags `v*`.
- Limites conhecidos: exe não assinado (SmartScreen avisa), possível falso positivo de antivírus, só Windows (no Linux/Mac o dev instala o Ollama), sem retomar download interrompido.

### Editor inteligente (caixa de notas)
O texto digitado pode misturar anotações novas e instruções sobre itens existentes (`editor.py`):
1. Cada linha passa por um detector determinístico (regex estrita + fuzzy para digitação). O modelo não decide o que é instrução: quando decidia, perdia anotações novas.
2. Cada instrução vai sozinha ao modelo (juntas, ele trocava os destinos) e volta só como ações.
3. A ação só vale se o item for citado na linha (≥60% das palavras do título).
4. Tudo é aplicado na hora e é reversível: "excluir" arquiva, e o diário `alteracao` alimenta o botão Desfazer. Duplicados são achados por regra (título normalizado, fica o mais novo).
5. Linhas sem instrução vão para o classificador. Instrução sem ação válida vai para Revisar, com "Tentar de novo" e "Guardar como anotação".
6. **Pedido em massa** ("separar melhor tudo que está em trabalho", verbo de organizar + "tudo/pasta/itens"): o modelo revisa a pasta de cada item do escopo (`em trabalho` = só essa pasta; sem pasta = todos os abertos). Só itens do escopo mudam, e tudo entra no diário.
7. **Aprende com você:** itens que mudaram de pasta e continuam lá (arraste, Mover, instrução, IA) viram exemplos no prompt do classificador e da reorganização (`db.exemplos`). Mover de novo corrige o exemplo; Desfazer o remove.
8. **Colagem do WhatsApp:** o cabeçalho `[hh:mm, dd/mm/aaaa] Nome:` sai do texto, e "amanhã"/"sex" contam a partir da data de cada mensagem. Dias abreviados (seg…dom) viram data.
9. **Sem repetidos:** item novo com o mesmo título (normalizado) de um item aberto não é criado.

Limite: lista em várias linhas com o destino só na última tem as primeiras linhas tratadas como anotações novas.

### Tela (opção B2 dos mockups em `docs/mockups/`)
- **Lateral de pastas** (no celular vira trilho): Hoje, as pastas (= `contexto`), Revisar e Lixeira. As pastas são alvo de arraste.
- **Pastas do usuário** (tabela `pasta`, semeada com as 7 padrão): "+ Nova pasta" cria com nome e descrição; a descrição vai para o prompt e o slug entra no enum do JSON Schema de cada chamada, então a IA passa a usar a pasta nova na hora. "Apagar pasta" pede o destino dos itens (outra pasta ou Lixeira) e nunca apaga item junto. Outro não pode ser apagada; nomes de tela (Hoje, Revisar, Lixeira) são recusados.
- **Hoje:** atrasados e prazos do dia de todas as pastas.
- **Pasta = grade livre de 4 colunas:** o card pode ir para qualquer célula (pode deixar buracos) e crescer pelo canto até 4x4. Nada se sobrepõe: quem estava no lugar desce. A posição e o tamanho ficam em `item.grade_*` (`POST /api/layout`). Mudar de pasta zera a posição. No celular a grade vira lista nessa ordem.
- **Arrastar:** com o mouse, na hora; no toque, depois de segurar 300 ms (mexer antes disso é rolagem). "Mover para…" no card faz o mesmo sem arraste.
- **Criticidade:** crítica, alta, média e baixa. A regra sugere de alta a baixa pelo prazo; só o usuário marca crítica, e a escolha manual não é recalculada.
- **Feito, Excluir, Restaurar, Mover e criticidade** passam por `POST /api/itens/editar`, o mesmo validador das ações da IA, com diário e aviso com Desfazer.
- **Seleção múltipla:** clique marca um card (como no Explorer), Ctrl+clique soma ou tira, Shift+clique marca o intervalo (na ordem da tela), segurar no espaço vazio e arrastar desenha um laço que marca os cards tocados (com Ctrl/Shift, soma), Ctrl+A marca todos, Esc limpa e Delete manda para a Lixeira. No celular, o botão "Selecionar" faz o toque marcar. A barra aplica Feito, Mover, Criticidade ou Excluir em todos (`POST /api/itens/editar` com `ids`: tudo ou nada, um Desfazer). Arrastar um card marcado leva a seleção inteira para a pasta.
- **+ Nova:** tarefa criada à mão, sem IA (`POST /api/itens`). Prazo em texto livre ("sexta 14h") pelas mesmas regras; criticidade automática pelo prazo ou escolhida.
- **Lixeira:** Excluir arquiva. "Apagar de vez" e "Esvaziar" pedem confirmação, removem o item e o diário dele e reescrevem a nota original sem o texto apagado (ou apagam a nota, se era o último item).

### Janela flutuante da IA
Pergunta sobre as notas e pede mudanças ("marca a conta de luz como feita", "adia o dentista pra segunda", "anota que..."). As ações (criar, estado, prazo, contexto, prioridade) são validadas pelo servidor (item existe, enum válido, data resolvida por regra), precisam citar o item no pedido ou no turno anterior e são **aplicadas na hora com Desfazer**. Não existe ação de apagar de vez. Texto de nota é tratado como dado não confiável (prompt injection). Limitação medida: o 7B erra contas de data, então a lista enviada ao modelo já traz dia da semana e "amanhã/em N dias"; ainda pode sobre-incluir itens em perguntas vagas ("o que tenho hoje?").

### Modelo de dados atual (servidor, `db.py`)
- `captura(id UUID do cliente, texto, origem[web|chat|editor|manual], criado_em, status[pendente|ok|falhou], erro)`: texto original; só muda em "Apagar de vez".
- `item(id, captura_id, tipo, titulo, contexto = slug da pasta, prazo_texto, prazo_em, prioridade[critica|alta|media|baixa], tags, estado[catalogado|feito|arquivado], criado_em, grade_col, grade_lin, grade_larg, grade_alt)`.
- `pasta(slug, nome, descricao, ordem, criado_em)`: semeada com as 7 padrão; `outro` é fixa.
- `alteracao(grupo, captura_id, item_id, campo, antes, depois, descricao, desfeito)`: diário de toda mudança da tela, do editor e da IA; um grupo = um Desfazer. Também é a fonte dos exemplos que a IA aprende (`db.exemplos`).
- `imagem(captura_id, dados)`: foto em base64 esperando a IA; apagada quando vira itens (captura `origem=imagem`).
- `classificacao(captura_id, modelo, prompt_v, latencia_ms, valido, erro)`: auditoria de cada chamada.

### Testes
- `tests/test_rules.py` (datas), `tests/test_api.py` (API, editor, IA com Ollama falso, pastas, lixeira), `tests/ui_browser.py` (tela real no Chrome headless, PC e celular com toque, banco temporário).

## Decisões (histórico, parte Android)
- **Android nativo (Kotlin), Android-only.** StatCounter jun-ago/2026: ~68% mundo, ~75-79% Brasil.
- **Arquitetura B:** IA só no PC (Python + Ollama). Celular captura offline, regras de data, alarmes locais (AlarmManager + boot receiver, `USE_EXACT_ALARM`), `allowBackup=false`.
- **Chat: Telegram** (long polling, allowlist de chat_id). Sem WhatsApp: Baileys arrisca ban; Cloud API exige número dedicado e webhook público.
- **Escritor único:** só o celular altera itens. PC devolve propostas append-only; chat gera capturas/comandos. `editado_mask` + `rev` impedem sobrescrever correção manual.
- **Datas por regra**, não por IA (modelos pequenos erram aritmética). Prioridade derivada por regra.
- **Room com FTS4** (FTS5 não é suportado). SQLCipher adiado.
- Resumo diário = notificação local (PC desligado não pode quebrar).
- IA no celular (llama.cpp, Qwen2.5-1.5B, GGUF baixado na 1ª execução) é experimento tardio com benchmark.

## Modelo de dados (alvo do app/PC)
- `captura(id UUIDv7, texto_original, origem[app|share|telegram], origem_msg_id UNIQUE, criado_em, status_proc)`
- `item(id, captura_id, tipo, titulo, contexto, prazo_em, prazo_texto, prioridade, estado[inbox|catalogado|feito|arquivado], rev, editado_mask, deleted_at, updated_at)`
- `item_tag(item_id, tag)`
- `classificacao(id, captura_id, modelo, prompt_v, texto_hash, payload_json, valido, latencia_ms, erro, aplicada_em)` — histórico/auditoria
- `comando(id, origem_msg_id UNIQUE, tipo, args_json, aplicado_em)`

Proposta só é aplicada se `base_rev == rev` atual e nunca sobrescreve campo marcado em `editado_mask`. Falha do modelo: 1 retry, depois a nota vai crua para "revisar" (nunca se perde).

## Fases
0. Classificador + harness no PC (**aqui**)
1. App Android fino: captura, Room+FTS4, regras em Kotlin, alarmes. Sem IA
2. Celular↔PC via FastAPI (capturas → propostas)
3. Bot Telegram
4. Experimento de IA no celular com benchmark
5. Extras: embeddings, OCR, export Obsidian, SQLCipher

## Pendências
- Regras em Kotlin e Python devem passar nos mesmos casos (`tests/` → fixture compartilhada).
- Dataset: crescer de 10 para 150-300 casos sintéticos + conjunto privado.
- Calibrar "confiança" por logprob do token do enum, não autodeclarada.
