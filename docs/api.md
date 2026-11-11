# API HTTP

Servidor FastAPI em `backend/dumpbox/api.py`. Tudo sob `/api`; o resto (`/`) serve a PWA de `web/`. JSON em português, erros no formato padrão do FastAPI: `{"detail": "mensagem"}`.

Documentação interativa gerada pelo FastAPI: `http://127.0.0.1:8000/docs`.

## Autenticação

- Usuário único. Senha guardada só como hash scrypt (`DUMPBOX_PASSWORD_HASH` em `config.env`).
- Login devolve o cookie `sess` (`HttpOnly`, `SameSite=Strict`, 7 dias; `Secure` se `DUMPBOX_COOKIE_SECURE=1`). Token assinado com HMAC usando `DUMPBOX_SECRET`; sem essa variável, um segredo novo é gerado a cada início e as sessões caem ao reiniciar.
- Rotas marcadas com 🔒 exigem o cookie; sem ele: `401 não autenticado`.
- Limite de login: 5 tentativas por minuto por IP (`429`). Fica em memória, vale para um processo.

## Públicas

| Método e rota | Corpo | Resposta |
|---|---|---|
| `GET /api/estado` | | `{"configurado": bool, "preparo": {fase, pct, msg, erro, modelo, pronto}}`. A tela usa para escolher entre criar senha, login e app, e para mostrar o download da IA. |
| `POST /api/setup` | `{"senha": "≥8 caracteres"}` | `{"ok": true}` + cookie. Só funciona **sem senha existente** (`409`) e **do próprio PC**: host loopback e nenhum cabeçalho de proxy/túnel (`X-Forwarded-For`, `Forwarded`, `X-Real-IP`, `CF-Connecting-IP`, `Tailscale-User-Login`), senão `403`. |
| `POST /api/login` | `{"senha": "..."}` | `{"ok": true}` + cookie. `401` senha errada, `429` limite, `503` sem senha configurada. |
| `POST /api/logout` | | `{"ok": true}`, apaga o cookie. |

## Capturas (texto bruto)

Uma captura é o texto como foi digitado. O worker classifica em segundo plano e gera itens; o texto original nunca é alterado (exceto em "Apagar de vez").

| Método e rota | Corpo | Resposta |
|---|---|---|
| 🔒 `GET /api/sessao` | | `{"ok": true}` se o cookie vale. |
| 🔒 `POST /api/capturas` | `{"id": "uuid do cliente (8-64)", "texto": "1-5000", "criado_em"?: "hora local da escrita"}` | `{"nova": bool}`. `criado_em` faz "amanhã" contar de quando a nota foi escrita (fila offline); fora de um ano atrás até agora, vale a hora do PC. Idempotente pelo `id`: reenviar a mesma captura (fila offline) devolve `nova: false` e não duplica. |
| 🔒 `POST /api/capturas/imagem` | `{"id", "imagem": "JPEG/PNG em base64 (≤4 MB)", "texto"?: "instruções (≤1000)", "criado_em"?}` | `{"nova": bool}`. Foto ou print de lista; `texto` orienta o classificador (tipo, pasta, prazo) e não vira item. O worker transcreve com o modelo de visão, a captura passa a ter o texto lido (`[x]` = marcado) e linhas que repetem um item aberto (≥60% das palavras nos dois sentidos) não viram item novo: marcadas fecham o item existente (diário, Desfazer), sem marca ficam como estão. As demais viram itens; marcadas entram como `feito`. A foto é apagada depois que vira itens. `422` se não for JPEG/PNG. |
| 🔒 `POST /api/capturas/{id}/reprocessar` | | Volta uma captura `falhou` para a fila. `404` se não existe ou não falhou. |
| 🔒 `POST /api/capturas/{id}/como-nota` | | Instrução que o editor não conseguiu aplicar: reprocessa tratando o texto como anotação comum. `404` como acima. |

Ciclo: `pendente` → (worker) → `ok` com itens, ou `falhou` com `erro` (aparece em Revisar). Enquanto a IA está sendo preparada, tudo fica `pendente`.

## Itens

| Método e rota | Corpo | Resposta |
|---|---|---|
| 🔒 `GET /api/itens` | | `{"itens": [...], "revisar": [...], "lixeira": [...], "pastas": [...]}`. `itens` = não arquivados, mais novos primeiro; `revisar` = capturas `pendente`/`falhou`; `lixeira` = arquivados. |
| 🔒 `POST /api/itens` | `{"titulo", "contexto"?: slug (padrão "outro"), "tipo"?: tarefa\|compromisso\|ideia\|compra\|nota, "prioridade"?: critica\|alta\|media\|baixa, "prazo"?: "sexta 14h"}` | `{"id", "descricao"}`. Criação manual, sem IA. Prazo resolvido por `rules.py`; data não entendida dá `422`. Sem `prioridade`, a regra calcula pelo prazo. |
| 🔒 `POST /api/itens/editar` | `{"ids": [1..500], "campo": "estado"\|"contexto"\|"prioridade", "valor": "..."}` | `{"grupo", "descricao", "n"}`. Feito, Excluir (`estado=arquivado`), Restaurar, Mover e criticidade, em um ou vários itens. Tudo ou nada: um id inválido dá `404`/`422` e nada muda. Um grupo = um Desfazer. |
| 🔒 `POST /api/layout` | `{"itens": [{"id", "col": 1-4, "lin": 1-1000, "larg": 1-4, "alt": 1-4}]}` | `{"ok": true}`. Posição e tamanho do card na grade da pasta. |
| 🔒 `POST /api/itens/{id}/apagar` | | Apaga de vez um item **que está na Lixeira** (`404` se não está). Remove o item e o diário dele e reescreve a captura sem o texto. |
| 🔒 `POST /api/lixeira/esvaziar` | | `{"apagados": n}`. |

Campos de `item`: `id, captura_id, tipo, titulo, contexto` (slug da pasta)`, prazo_texto, prazo_em` (`YYYY-MM-DD` ou `YYYY-MM-DDTHH:MM`)`, prioridade, tags` (JSON)`, estado` (`catalogado|feito|arquivado`)`, criado_em, grade_col, grade_lin, grade_larg, grade_alt`.

## Pastas

| Método e rota | Corpo | Resposta |
|---|---|---|
| 🔒 `POST /api/pastas` | `{"nome": "1-40", "descricao"?: "≤200"}` | `{"slug", "nome"}`. A descrição entra no prompt da IA; o slug entra no enum do JSON Schema da próxima chamada. Nome repetido ou reservado (Hoje, Revisar, Lixeira) dá `422`. |
| 🔒 `POST /api/pastas/{slug}/apagar` | `{"destino": "slug de outra pasta" \| "lixeira"}` | `{"movidos", "grupo", "descricao"}`. Os itens vão para o destino (com diário) e só então a pasta é removida. `outro` não pode ser apagada. |

## Diário e Desfazer

Toda mudança feita pela tela, pelo editor ou pela IA vai para a tabela `alteracao`, agrupada por `grupo`.

| Método e rota | Corpo | Resposta |
|---|---|---|
| 🔒 `GET /api/alteracoes` | | Últimos 8 grupos: `[{"grupo", "descricoes": [...], "desfeito": bool}]`. |
| 🔒 `POST /api/desfazer` | `{"grupo": "..."}` | `{"revertidas": n}`. Reverte de trás para frente e só mexe no campo se ele ainda estiver como a mudança deixou (não atropela edição posterior). |

## Chat com a IA

| Método e rota | Corpo | Resposta |
|---|---|---|
| 🔒 `POST /api/chat` | `{"mensagem": "1-1000", "historico"?: [{"role": "user"\|"assistant", "content"}] (até 6)}` | `{"resposta", "feitas": [descrições], "grupo": id ou null}`. Ações aplicadas na hora e reversíveis pelo `grupo`. `503` se o Ollama não responde. |

Ações possíveis da IA: `criar, estado, prazo, contexto, prioridade, titulo, tipo, deduplicar`. Cada uma é validada no servidor (item existe, valor no enum, data resolvida por regra) e o item precisa ter sido citado na mensagem ou no histórico; o resto é ignorado e contado na resposta. Não existe ação de apagar de vez.

## Exemplo com curl

```bash
curl -c c.txt -H 'Content-Type: application/json' -d '{"senha":"minha-senha"}' http://127.0.0.1:8000/api/login
curl -b c.txt -H 'Content-Type: application/json' \
     -d '{"id":"6f1c2a9e-0000-4000-8000-000000000001","texto":"comprar pão\ndentista sexta 14h"}' \
     http://127.0.0.1:8000/api/capturas
curl -b c.txt http://127.0.0.1:8000/api/itens
```
