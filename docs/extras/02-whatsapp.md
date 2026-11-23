# Extra 2: WhatsApp

## Objetivo
As mesmas quatro funções do bot do Telegram (nota, lembrete, `?` para a IA e
comandos), só que no WhatsApp. **Zero lógica nova**: o canal chama `canais/base.tratar`
e o `lembretes.py` passa a ter dois destinos.

Bônus que já existe: o classificador entende o formato de cópia do WhatsApp
(`classifier.blocos_zap`, datas relativas à hora da mensagem). Encaminhar uma conversa
para o próprio bot já funciona bem.

## Qual API usar

| Opção | Como conecta | Prós | Contras |
|-------|--------------|------|---------|
| **Evolution API** (recomendada para uso pessoal) | Container Docker local, pareia por QR como o WhatsApp Web, avisa o dumpbox por webhook **em localhost** | Não expõe o PC, sem custo, sem aprovação da Meta. Ainda treina Docker (item 4 da lista de estudo) | Não oficial: viola os termos do WhatsApp e há risco de bloqueio do número. **Usar um número separado, nunca o principal** |
| **WhatsApp Cloud API** (oficial, Meta) | Webhook público HTTPS (precisa de Tailscale Funnel ou VPS) + token de app da Meta | Oficial, é o que cliente de freelance pede | Conta Meta Business, número verificado, janela de 24 h, templates aprovados para mensagem iniciada pelo bot (o lembrete precisa de template) |

Decisão: **implementar a interface pela Evolution primeiro** (mais rápido de provar) e
deixar `canais/whatsapp.py` com duas classes pequenas e o mesmo contrato:
`receber(payload) -> (remetente, msg_id, texto)` e `enviar(numero, texto)`. Trocar para
a Cloud API depois é trocar a classe e a configuração, não o resto.

## Arquivos

| Arquivo | O que faz |
|---------|-----------|
| `backend/dumpbox/canais/whatsapp.py` | `Evolution` e `CloudAPI`, ~60 linhas cada. |
| `api.py` | `POST /api/canais/whatsapp` (webhook). Autenticação por segredo compartilhado no header (`DUMPBOX_ZAP_SEGREDO`), não pelo login da tela. Na Cloud API: `GET` de verificação (`hub.challenge`) + checagem da assinatura `X-Hub-Signature-256` (HMAC do corpo com o app secret). |
| `extras/evolution/docker-compose.yml` | Sobe a Evolution API com volume em `D:\`, nunca em `C:\`. |
| `lembretes.py` | `DUMPBOX_AVISOS=telegram,whatsapp` escolhe os destinos. |

## Fluxo

```
WhatsApp ─► Evolution (Docker) ─► POST localhost:8000/api/canais/whatsapp
              header segredo ok?  não → 401
              evento ≠ mensagem recebida, ou mensagem enviada por mim → 200 e ignora
              remetente ∉ DUMPBOX_ZAP_PERMITIDOS → 200 e ignora
              base.tratar(c, "whatsapp", numero, msg_id, texto) → resposta
              Evolution.enviar(numero, resposta)
```
Webhook responde 200 rápido. A resposta vai por chamada separada (a Meta reenvia se
demorar mais de ~10 s).

## Cuidados específicos
- **Loop**: o webhook também recebe as mensagens que o bot envia (`fromMe`). Ignorar
  sempre, senão o bot responde a si mesmo.
- **Cloud API, janela de 24 h**: fora dela só vai template aprovado. O lembrete precisa
  de um template "lembrete_tarefa" com variável `{{1}}`. Documentar isso no README.
- **Áudio e foto**: fora de escopo. Responder "só texto por enquanto".
- **Número no log**: guardar só os 4 últimos dígitos (LGPD).

## Testes
- Payloads de exemplo da Evolution e da Cloud API **inventados** em `tests/dados/`.
- Segredo errado dá 401, `fromMe` é ignorado, mensagem duplicada (mesmo `msg_id`) não
  duplica, e com a Cloud API a assinatura inválida dá 401.
- Mesma bateria de `base.tratar` do Telegram (já coberta).

## Pronto quando
- [ ] Nota e encaminhamento de conversa pelo WhatsApp viram itens
- [ ] Lembrete chega pelo WhatsApp (Evolution)
- [ ] Classe `CloudAPI` com teste de assinatura, mesmo sem conta Meta ativa
- [ ] README: aviso do risco da Evolution + passo a passo do Docker

## Fora de escopo
Grupos, mídia, múltiplos usuários, envio em massa, template de marketing.
