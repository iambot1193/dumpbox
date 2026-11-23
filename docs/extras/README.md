# Extras: Telegram, WhatsApp e "perguntar às notas"

Plano de três extensões do dumpbox. Cada arquivo é o projeto de uma fase, com o que entra, onde mexe no código, como testar
e o que fica de fora. **Status:** 1 (Telegram) implementado; 2 e 3 só planejados.

| # | Extra | Arquivo | Esforço | Depende de |
|---|-------|---------|---------|------------|
| 1 | Bot Telegram (captura + lembretes + chat) | [01-telegram.md](01-telegram.md) | 1–2 dias | nada |
| 2 | WhatsApp (mesmas funções do bot) | [02-whatsapp.md](02-whatsapp.md) | 1–2 dias | 1 (reusa o adaptador) |
| 3 | Perguntar às notas (RAG + ferramentas + memória) | [03-rag-ferramentas.md](03-rag-ferramentas.md) | 3–5 dias | nada (melhora 1 e 2) |

Ordem: **Telegram primeiro**. A API é a mais simples e funciona por *long polling*, sem
expor o PC na internet, e o lembrete pelo Telegram já estava previsto
(`docs/arquitetura.md`, fase 3). O WhatsApp reaproveita o mesmo adaptador. O RAG vem
por último porque é o mais fundo e deixa os dois bots mais úteis.

## Ideia central: um adaptador, vários canais

Hoje toda nota entra por `db.nova_captura(c, id, texto, origem=...)` e o worker
(`api._worker`) classifica. A coluna `captura.origem` já existe (`'web'`). Os bots
**não ganham lógica própria**. Eles só traduzem mensagens:

```
Telegram ─┐                       ┌─ db.nova_captura(origem="telegram")  → worker classifica
          ├─ canais/base.py ──────┼─ chat.conversar()  (mensagem começando com "?")
WhatsApp ─┘   (roteia o texto)    └─ comandos fixos (/hoje, /desfazer)
                                     ▲
lembretes.py (thread) ───────────────┘ envia aviso pelo canal configurado
```

Regras que valem para os três extras (as mesmas do projeto, ver `CLAUDE.md`):

- **Só o dono fala com o bot**: lista de IDs permitidos (`DUMPBOX_TG_PERMITIDOS`,
  `DUMPBOX_ZAP_PERMITIDOS`). Mensagem de outra pessoa é ignorada sem resposta.
- **Texto da mensagem é não confiável**: passa pelo mesmo caminho da tela
  (`chat.validar`, ações só sobre item citado, sempre reversíveis). Apagar de vez
  continua só pela Lixeira.
- **Datas e prioridade por regra** (`rules.py`), nunca pela IA.
- **Segredos em `<home>/config.env`** (como a senha), nunca no repositório.
- **Idempotência**: o id da captura vem do id da mensagem (`tg-<chat>-<msg>`,
  `zap-<id>`). Se a mensagem chegar duas vezes, ela não vira dois itens.
- **Repo público**: testes e exemplos com mensagens inventadas.

## O que isso prova no currículo

- Integração com API de mensageria (webhook e polling, idempotência, lista de permitidos).
- Mesmo núcleo atendendo três canais: arquitetura de adaptador, sem duplicar regra.
- RAG local com embeddings no SQLite, chamada de ferramentas e avaliação medida, que
  são os temas das vagas de "agente de IA".

Só escrever "já fiz" depois que a fase estiver no repositório, com teste e print.
