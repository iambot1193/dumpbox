# Extra 1: bot do Telegram

> **Implementado.** Ligar: crie o bot no @BotFather e rode
> `PYTHONPATH=backend python -m dumpbox.canais.telegram` (grava token e seu chat_id no `config.env`),
> depois reinicie o dumpbox. Resumo diário opcional: `DUMPBOX_TG_RESUMO=08:00` no `config.env`.
> Diferenças do plano: offset em `<home>/telegram.offset`; `avisado_em` volta a nulo por um
> *trigger* do SQLite (cobre tela, sync, IA e desfazer sem mexer em cada caminho).

## Objetivo
Pelo Telegram, sem abrir o app:
1. **Despejar nota**: qualquer texto vira captura (igual à caixa de notas).
2. **Receber lembrete**: o aviso do `item.lembrete` e o resumo diário chegam no celular,
   mesmo com a PWA fechada (hoje o aviso depende da aba aberta).
3. **Pedir à IA**: mensagem começando com `?` vai para `chat.conversar`
   ("? passa o dentista pra sexta").
4. **Comandos fixos**: `/hoje`, `/atrasados`, `/desfazer`.

## Por que long polling
`getUpdates` com timeout de 30 s: o PC **pergunta** ao Telegram, e o Telegram não
precisa chamar o PC. Não precisa de IP público, Funnel nem certificado. Combina com
"servidor no PC atrás do Tailscale". O webhook fica para quando houver VPS.

## Dependência
Nenhuma nova: a Bot API é HTTP simples e o projeto já tem `httpx`. Não usar
`python-telegram-bot` (seria mais uma dependência e um loop assíncrono à parte).

## Arquivos

| Arquivo | O que faz |
|---------|-----------|
| `backend/dumpbox/canais/base.py` | `tratar(c, canal, remetente, msg_id, texto) -> str`: decide entre captura, chat ou comando e devolve a resposta. Compartilhado com o WhatsApp. |
| `backend/dumpbox/canais/telegram.py` | Thread de polling + `enviar(chat_id, texto)`. ~80 linhas. |
| `backend/dumpbox/lembretes.py` | Thread que, a cada minuto, acha itens com `prazo_em - lembrete <= agora` ainda não avisados e chama `enviar` do canal configurado. |
| `api.py` (`lifespan`) | Sobe as threads se `DUMPBOX_TG_TOKEN` existir. Sem token, nada muda. |
| `db.py` | Coluna `item.avisado_em TEXT` (migração no padrão `ALTER TABLE` já usado) e o valor `'telegram'` em `captura.origem`. |
| `setup.py` | Pergunta opcional do token e do seu chat_id, gravados em `config.env`. |

## Fluxo de uma mensagem

```
getUpdates(offset) ──► update.message
   remetente ∉ DUMPBOX_TG_PERMITIDOS?  ──► ignora (sem resposta, sem log do texto)
   base.tratar(...)
     "/hoje"      → lista curta de db (atrasados + hoje)
     "/desfazer"  → chat.desfazer(último grupo do canal)
     "? ..."      → chat.conversar(c, texto, historico_do_canal)
     outro texto  → db.nova_captura(id=f"tg-{chat}-{msg}", origem="telegram")
                    responde "anotado ✓"; quando o worker terminar, manda os itens criados
   offset = update_id + 1  (salvo em config, então reiniciar não repete mensagens)
```

## Lembretes (servem para os dois bots)
- Consulta: `estado` aberto, `prazo_em` definido e `avisado_em` nulo, com
  `prazo_em - lembrete min <= agora`.
- Envia, depois grava `avisado_em`. Se o envio falhar, não grava e tenta de novo no
  próximo minuto.
- Se mudar o prazo ou o lembrete pela tela/sync, `avisado_em` volta a nulo. O ponto
  único é `chat._mudar` (por onde passam tela, sync e IA). Conferir também o caminho
  de `api._valor_direto` para o campo `lembrete`.
- Item com `repete`: `chat._repetir` cria a próxima ocorrência, que nasce com
  `avisado_em` nulo.
- Resumo diário no horário já configurado na tela (lembrete diário).
- PC desligado: o aviso sai quando ligar ("atrasado: ..."), não se perde.

## Segurança
- Token só em `config.env`. Ele dá controle total do bot, então nunca vai para log ou commit.
- `DUMPBOX_TG_PERMITIDOS`: lista de chat_id. O `setup` descobre o seu pelo primeiro `/start`.
- Limite de 20 mensagens/min por remetente (contador em memória). Passou disso, ignora.
- Resposta do bot nunca reproduz nota de outra pasta sem ter sido pedida.

## Testes (sem rede)
- `tests/test_canais.py`: `base.tratar` com textos inventados. Captura criada com a
  origem certa, mensagem repetida não duplica, `?` vai ao chat (com Ollama falso),
  remetente fora da lista é ignorado.
- `lembretes`: relógio injetado (`agora=`). Avisa uma vez, reavisa depois de mudar o
  prazo, falha no envio mantém pendente.
- `telegram.py`: `httpx.MockTransport` com um `getUpdates` gravado (dados inventados).

## Pronto quando
- [ ] Nota pelo Telegram aparece na tela classificada
- [ ] Lembrete chega com a PWA fechada
- [ ] `? marca o X como feito` funciona e `/desfazer` reverte
- [x] Testes passando (`tests/test_canais.py`); README com print do chat (conversa inventada)

## Fora de escopo agora
Webhook, grupos, botões inline (dá para adicionar depois: concluir pelo botão do
aviso), foto pelo Telegram (seria fácil, porque `visao.py` já existe; fica como 1.1).
