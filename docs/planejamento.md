# Planejamento completo (10/11/2026)

Histórico das ideias, decisões e a revisão crítica. Decisões finais em `arquitetura.md`.

## 1. Ideia original
App pessoal (e de portfólio, repo público no GitHub) de lembretes/afazeres: escreve-se texto solto no celular, toca em "agendar armazenamento", o texto entra numa fila e uma IA cataloga (tipo, título, prioridade, prazo, categoria, tags), separa um dump em vários itens e pontua. Entrada extra por chat. Servidor no PC pessoal, assíncrono: o celular guarda e espera o PC ficar disponível.

## 2. Evolução das decisões
| Pergunta | Resposta |
|---|---|
| Servidor no celular, IA no celular, 100% offline? | Possível com modelo 1-1.5B Q4 (llama.cpp), mas lento no Moto G84 (Snapdragon 695, 8 GB, sem NPU/GPU útil). Ficou como experimento tardio |
| Kotlin vs Flutter vs PWA+Termux | **Kotlin nativo**: alarme exato, widget, background e IA local confiáveis. Termux é morto pelo Android; PWA não tem alarme exato |
| Foco só Android? | Sim. StatCounter jun-ago/2026: Android ~67-69% mundo, ~75-79% Brasil. iOS custaria Mac + conta paga |
| Chat de entrada | **Telegram** (oficial, grátis, long polling, sem ban). WhatsApp descartado: Baileys arrisca banir o número; Cloud API exige número dedicado, webhook público e template pago, e proíbe chatbot de IA de uso geral desde 01/2026 |
| Arquitetura | **B**: IA só no PC; celular captura offline + regras + alarmes locais |

## 3. Revisão crítica (subagente Opus, esforço high)
Achados principais, todos incorporados:
- **Sync multi-master disfarçado** → escritor único (só o celular altera itens); PC gera propostas append-only; chat gera capturas/comandos; `editado_mask` + `rev`.
- **Latência real** 30-90 s/nota no 695 (estimativa; o prompt de entrada domina) → medir com `llama-bench` antes de prometer.
- **Syncthing em SQLite** corrompe (WAL) e o app Android foi descontinuado → removido.
- **MediaPipe LLM** em manutenção → llama.cpp.
- **Room só tem FTS4** (sem FTS5) → FTS4; SQLCipher adiado.
- **Auto Backup** manda o banco pro Google Drive → `allowBackup=false`.
- **Datas por IA** erram (aritmética) → modelo copia o trecho, parser determinístico resolve.
- Lembretes: receiver de boot, `POST_NOTIFICATIONS`, `USE_EXACT_ALARM`; resumo diário como notificação local.
- Licenças: Qwen2.5-1.5B é Apache 2.0; **3B não é**. GGUF baixado na 1ª execução, nunca no repo.
- Portfólio para vaga Python/dados/IA: o valor está no **harness de avaliação**, não no Kotlin. Dataset 150-300 casos: sintético público + real privado.
- Cortados: Syncthing, Docker Compose (só Dockerfile), Whisper, MediaPipe, Evolution, urgência/impacto por IA no celular.

Itens marcados como verificados vs estimativa estão na revisão original (resumida acima).

## 4. Ideias que ficaram na lista
- Fase 5: embeddings/duplicatas, OCR, export Obsidian, SQLCipher, busca semântica.
- Few-shot aprendido das correções (só no PC).
- Destilar/LoRA para modelo pequeno (diferencial de portfólio).
- Confiança calibrada por logprob do token do enum.
- **Entrada por imagem** → ver `visao-imagem.md`.

## 5. Fases
0. Classificador + harness no PC (**criado**, falta benchmark)
1. App Android fino (captura, Room+FTS4, regras, alarmes)
2. Celular↔PC via FastAPI
3. Bot Telegram
4. Experimento de IA no celular
5. Extras (imagem, embeddings, OCR…)
