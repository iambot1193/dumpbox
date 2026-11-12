# Plano: celular offline-first com sincronização pelo Tailscale

Status: **decidido em 2026-11-11, não implementado.** Variante A (réplica + fila de alterações).
Itens marcados **[celular]** só podem ser testados com o aparelho na bancada.

## Objetivo
Usar o app no celular por dias, com ou sem o PC ligado, e ver tudo no PC depois, sem mexer em arquivo nenhum.

## Como funciona
- O PC (SQLite) continua sendo a fonte da verdade e o único lugar com IA.
- O celular guarda uma **cópia** do último `/api/estado` (IndexedDB) e mostra essa cópia quando o PC não responde.
- Toda mudança feita offline (Feito, Excluir, Mover, Criticidade, Editar, arrastar na grade) aparece na hora na tela
  e entra numa **fila de alterações**: `{id único, item_id, campo, valor, quando}`.
- Ao reconectar, o celular envia a fila para `POST /api/sync`, e depois puxa o `/api/estado` inteiro de novo.
- Notas novas continuam na fila de capturas que já existe; a IA classifica quando o PC recebe.

## Regra de conflito: o mais recente vence, **por campo**
Não é sobrescrever o banco nem o card inteiro. Cada campo de cada item é comparado sozinho:
- O servidor sabe quando cada campo mudou pela última vez (diário `alteracao`; ou `criado_em` do item se nunca mudou).
- Alteração da fila com `quando` mais novo que a última do servidor naquele campo: aplica.
  Mais velha: descarta e conta como "ignorada por ser mais antiga".
- Exemplo: segunda no celular (offline) você muda o **título** do #12; terça no PC muda a **pasta** do #12.
  Ao sincronizar, ficam os dois: título do celular e pasta do PC.
- Mesmo campo nos dois lados: fica o mais recente. O perdedor não some: tudo aplicado entra no diário, com Desfazer.
- `id único` repetido (reenvio após queda de rede) é ignorado: nada aplica duas vezes.
- Relógio do celular errado: a cada sincronização o celular manda a própria hora; o servidor calcula a diferença
  e corrige o `quando` de todas as alterações daquele envio.
- Excluir = `estado=arquivado` (campo comum), então segue a mesma regra. "Apagar de vez" só na Lixeira com o PC online.

## O que funciona sem o PC
| Funciona | Não funciona (espera o PC) |
|---|---|
| Ver todos os cards da última cópia | Classificar nota nova (fica "pendente") |
| Criar nota (fila) | Chat, instruções da caixa de notas, foto de lista |
| Feito, Excluir, Mover, Criticidade, Editar, grade | Apagar de vez, criar ou apagar pasta |
| Desfazer de algo ainda na fila (tira da fila) | Desfazer de algo já sincronizado sem o PC |

## Etapas
### 0. Pré-requisito: HTTPS pelo Tailscale **[celular]**
Service worker e armazenamento offline só rodam em HTTPS (ou localhost). Pelo IP `http://100.x.x.x` o modo offline não liga.
1. PC: `tailscale serve --bg 8000` → endereço `https://<nome-do-pc>.<tailnet>.ts.net`.
2. Celular com Tailscale ativo: abrir esse endereço, entrar, "Adicionar à tela inicial".
3. Conferir: com o PC ligado, desligar o Wi-Fi e o 4G do celular e reabrir o app: a tela abre (hoje já deve abrir o casco).

### 1. Servidor
- `POST /api/sync`: recebe `{agora_cliente, alteracoes: [...]}`, aplica a regra acima pelo `chat.validar`/`chat.aplicar`
  (mesmas validações da tela e da IA), devolve `{aplicadas, ignoradas_antigas, invalidas}`.
- Tabela `sync_recebido(id)` para ids já aplicados.
- Rotas de edição atuais ficam como estão (PC continua online direto).

### 2. Celular (web/app.js)
- Cópia do `/api/estado` no IndexedDB a cada atualização bem-sucedida; mostrar a cópia quando a API falhar.
- Ações de edição: se a API falhar por rede, aplicar na cópia local + fila; se der certo, fluxo de hoje.
- Faixa: "N alterações aguardando o PC" (junto da fila de notas que já existe).
- Ao reconectar: enviar fila de notas, enviar fila de alterações, puxar estado.

### 3. Testes automáticos (sem celular)
- `tests/test_api.py`: campos diferentes nos dois lados (ficam os dois); mesmo campo (vence o mais novo);
  id repetido (não aplica 2x); relógio do cliente 1 h adiantado (corrigido); valor inválido (rejeitado, resto aplica).
- `tests/ui_browser.py`: Playwright com `context.set_offline(True)`: editar, recarregar, ver cópia + faixa;
  voltar online: fila zera e o banco tem a mudança.

## Roteiro de teste na bancada **[celular]**
1. [ ] Etapa 0 completa: app instalado pelo endereço `https://...ts.net`.
2. [ ] Celular em modo avião: app abre e mostra os cards da última cópia.
3. [ ] Offline: marcar um item como feito, mover outro, editar o título de um terceiro, criar uma nota. Faixa mostra 3 alterações + 1 nota.
4. [ ] Fechar e reabrir o app ainda offline: mudanças e faixa continuam lá.
5. [ ] No PC, enquanto o celular está offline: mudar a pasta do item cujo título foi editado no celular.
6. [ ] Religar a rede no celular: faixa zera; no PC aparecem as 3 mudanças, a nota classificada, e o item editado ficou com título do celular **e** pasta do PC.
7. [ ] Conflito no mesmo campo: offline, mudar criticidade do item X para alta; depois, no PC, mudar para baixa. Reconectar: fica baixa (PC mais recente) e o diário mostra as duas.
8. [ ] Queda no meio: desligar a rede durante a sincronização; religar: nada duplicado.
9. [ ] PC desligado de verdade (não só o celular offline): mesmo comportamento do passo 2-4.
10. [ ] Relógio do celular adiantado 1 h (ajuste manual): repetir o passo 7, resultado correto.

## Riscos
- Cópia velha por dias: mitigado por puxar o estado inteiro após cada sincronização.
- Navegador do celular limpar o armazenamento (pouco espaço): fila perdida. Mitigação: PWA instalada e `navigator.storage.persist()`.
- Itens criados offline só viram card depois que o PC classifica (não há id antes disso).

## Depois disso (fora deste plano)
- Atualizar `CLAUDE.md` e `docs/arquitetura.md` se alguma regra mudar.
- QR "Conectar celular" no exe, apontando para o endereço `ts.net`.
