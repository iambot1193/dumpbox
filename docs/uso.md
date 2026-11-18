# Guia de uso

Como usar a tela do dumpbox no dia a dia. Para instalar, veja o [README](../README.md#usar-windows-sem-instalar-nada).

## Primeiro acesso

1. Abra o app no próprio PC (`http://127.0.0.1:8000`, ou o exe abre sozinho).
2. Crie uma senha (mínimo 8 caracteres). Ela só pode ser criada no PC, nunca por outro aparelho.
3. Na primeira vez, a IA é baixada (barra de progresso no topo). Pode anotar enquanto isso: as notas ficam em **Revisar** como pendentes e são classificadas quando a IA ficar pronta.

## Anotar

Escreva na caixa de notas e envie. Pode ser bagunçado, várias coisas juntas:

```
comprar pão e leite
dentista sexta 14h
ideia: app pra dividir conta do bar
pagar boleto da luz até dia 20
```

A IA separa em itens, escolhe tipo (tarefa, compromisso, ideia, compra, nota) e pasta. A data é resolvida por regra, não pela IA: "sexta 14h", "amanhã", "dia 20", "seg" viram data de verdade. A criticidade sai do prazo.

- **Sem internet ou com o PC desligado:** a nota fica guardada no navegador e é enviada sozinha quando o servidor voltar. Nada é enviado duas vezes.
- **A IA falhou?** A nota vai para **Revisar** com o texto original, e o botão **Tentar de novo** coloca na fila outra vez.
- **Repetido:** se já existe um item aberto com o mesmo título, outro não é criado.
- **Colagem do WhatsApp:** cole as mensagens como estão. O cabeçalho `[hora, data] Nome:` é removido e "amanhã" conta a partir da data da mensagem.

## Foto de uma lista

O botão de câmera ao lado de **Guardar** anexa uma foto ou print de lista ou checklist; no PC, dá para colar um print com **Ctrl+V** (ex.: depois de Win+Shift+S). A miniatura aparece na caixa e nada é enviado ainda: escreva instruções se quiser ("tudo do trabalho, pra sexta") e aperte Guardar. A IA lê cada linha e cria os itens: o que tem a caixa marcada (✓ ou X) já entra como feito. Leva uns 10 a 30 segundos no PC.

- Linha que já é um item seu não vira item novo: se está marcada na foto, o item é marcado como feito (com Desfazer); sem marca, fica como está. Serve para dar baixa mandando o print da lista.
- Funciona melhor com print ou foto reta e com boa luz. Texto riscado às vezes passa como não feito.
- A foto é reduzida no celular, e o PC apaga a foto depois de criar os itens. Fica só o texto lido.
- Sem conexão, a foto espera na fila como as notas.

## Dar instruções pela caixa de notas

Linhas que são instrução mexem nos itens existentes em vez de criar novos. Podem vir misturadas com anotações:

```
mover dentista para saúde
marcar conta de luz como feita
excluir os duplicados
separar melhor tudo que está em trabalho
comprar café
```

- O item precisa ser citado na linha (boa parte das palavras do título).
- "Separar melhor tudo que está em X" faz a IA revisar a pasta de cada item de X. Sem pasta, revisa todos os abertos.
- Tudo é aplicado na hora e aparece um aviso com **Desfazer**. "Excluir" manda para a Lixeira.
- Se a instrução não deu em nada, ela vai para Revisar com **Tentar de novo** e **Guardar como anotação**.

## A tela

- **Hoje:** atrasados e prazos do dia, de todas as pastas.
- **Pastas:** cada uma é uma grade de 4 colunas. Arraste o card para qualquer célula e aumente pelo canto (até 4x4). No celular, segure 300 ms antes de arrastar; a grade vira lista.
- **+ Nova pasta:** nome e descrição do que entra nela. A IA passa a usar a pasta na hora. Ao apagar uma pasta, você escolhe para onde vão os itens (outra pasta ou Lixeira). A pasta Outro não pode ser apagada.
- **+ Nova:** cria uma tarefa à mão, sem IA, com prazo em texto livre.
- **Criticidade:** crítica, alta, média, baixa. A regra sugere pelo prazo; só você marca crítica, e o que você marca não é recalculado. Há filtro por nível.
- **Revisar:** notas pendentes ou que falharam.
- **Lixeira:** itens excluídos. **Restaurar**, **Apagar de vez** ou **Esvaziar** (pedem confirmação e não têm volta).

### A IA aprende com você

Quando você muda um item de pasta (arrastando, pelo menu ou por instrução) e ele fica lá, isso vira exemplo para as próximas notas. Mudar de novo corrige o exemplo; Desfazer remove.

## Seleção múltipla

| Ação | PC | Celular |
|---|---|---|
| Marcar um | clique | botão **Selecionar**, depois toque |
| Somar ou tirar | Ctrl+clique | toque |
| Intervalo | Shift+clique | |
| Laço | arrastar no espaço vazio | |
| Pincel | Shift + segurar o botão sobre um card e passar o mouse pelos outros | |
| Todos / limpar | Ctrl+A / Esc | |
| Excluir | Delete | barra de ações |

A barra aplica Feito, Mover, Criticidade ou Excluir em todos de uma vez, com um só Desfazer. Arrastar um card marcado leva a seleção inteira.

## Janela da IA

O botão flutuante abre um chat sobre suas notas:

- Perguntas: "o que tenho pra sexta?", "quais compras estão abertas?"
- Pedidos: "marca a conta de luz como feita", "adia o dentista pra segunda", "anota que preciso ligar pro banco".

As mudanças são aplicadas na hora e têm Desfazer. A IA nunca apaga de vez e só mexe em item citado na conversa. Ela pode errar em perguntas vagas ("o que tenho hoje?"): para prazos, a vista **Hoje** é a fonte confiável.

## Usar no celular

1. Deixe o PC ligado com o dumpbox aberto.
2. Acesse pela mesma rede Wi-Fi ou por VPN privada (Tailscale). Detalhes no [README](../README.md#acessar-de-outro-aparelho-opcional).
3. No navegador do celular: menu → **Adicionar à tela inicial**. Vira um app.

Sem o PC ligado, o celular ainda guarda notas e envia depois, mas não mostra os itens.

## Atalhos novos (17/11/2026)
- **Celular, gestos no card:** segurar parado liga a seleção (toques seguintes somam); segurar e mover arrasta: solte sobre outro card para trocar os dois de lugar, ou sobre uma pasta para mover. Deslizar para a direita conclui (ou reabre, se já estava feito).
- **Compartilhar para o dumpbox (Android, app instalado):** no menu Compartilhar de qualquer app, escolha dumpbox; o texto/link chega na caixa de nota para você conferir e Guardar. Segurar o ícone do app mostra o atalho "Nova nota".
- **Ditar:** botão do microfone ao lado da câmera. No Chrome, o áudio vai para o serviço de voz do Google (é a única parte que sai do aparelho).
- **Busca:** campo abaixo da caixa de nota; procura em todas as pastas, sem diferenciar acento e maiúscula. Trocar de pasta limpa a busca.
- **Repetir:** no Nova/Editar, "Repetir" todo dia, toda semana ou todo mês. Ao concluir, a próxima é criada com o prazo seguinte (mês curto usa o último dia). O Desfazer reabre a antiga e manda a nova para a Lixeira.
- **Cópia para o celular:** botão "cópia p/ celular" na lateral (só no PC) baixa o arquivo para Importar cópia no modo celular.

## Novidades (18/11/2026)
- **Tutorial guiado:** abre no 1º acesso (depois pelo "ajuda" da lateral). Destaca a parte da tela e espera você fazer (guardar uma nota, criar pelo +, concluir); "Pular passo" segue sem fazer. A tela continua usável durante o tutorial.
- **Texto do card:** campo abaixo do título no Nova/Editar; aparece no card e entra na busca.
- **Prazo pelo calendário:** dia e hora (opcional) no Nova/Editar; o campo escrito ("sexta 14h") vale se preenchido. Apagar o dia tira o prazo.
- **Avisos de atraso:** "ligar avisos" (lateral ou último passo do tutorial). Tarefa que passa do prazo vira notificação, uma vez por prazo. Só com o app aberto ou em segundo plano.
- **Deslizar para concluir:** faixa verde atrás do card; ao passar do ponto fica marcada e o card sai deslizando.
- **Copiar e colar cards:** ícone de copiar no card, ou "Copiar" na barra da seleção (Ctrl+C). Vai como texto pronto para WhatsApp: pasta em *negrito*, `☐ título` (feito: `✅ ~título~`), etiqueta em _itálico_ (tipo · criticidade · 📅 dd/mm/aaaa hh:mm · 🔁 repetição) e o texto do card recuado. "Colar" (ou Ctrl+V fora das caixas) cria um card por linha de qualquer texto; lê esse formato e o antigo `- [ ] Título (…)`; sem pasta vai para a pasta aberta.
- **Avisos na tela não bloqueiam:** o aviso de baixo fica meio transparente e o clique passa por ele (só o Desfazer é botão).
- **Concluir pelo ✓:** o card risca, brilha em verde e some antes de gravar.

## Novidades (18/11/2026, tarde)
- **Dois botões de criar:** **+ Nova** abre o formulário completo (pasta, prazo, texto, check-list, repetir). **⚡ Rápida** (laranja) abre uma linha no topo: escreva e Enter cria e já deixa pronta para a próxima; `Pagar luz @ sexta 14h` põe prazo; "mais opções" leva o título para o formulário completo. Esc ou ✕ fecha.
- **Check-list:** no Nova/Editar, "+ item de check-list" cria um campo por item: Enter cria o próximo, Backspace no campo vazio apaga, × tira. No card vira caixinhas marcáveis com contador (☑ 2/5); marcar grava na hora, sem concluir o card. (Fica salvo no texto como linhas `[ ] item`; digitar assim também funciona.)
- **Celular em 2 colunas:** cards de criticidade alta/crítica ocupam a linha toda; os outros, meia. Puxe o canto (riscos no canto de baixo) para a direita = inteiro, para a esquerda = meio, para baixo/cima = altura (1 a 4). O tamanho vale também no PC (inteiro no celular = largura 2+ lá).
