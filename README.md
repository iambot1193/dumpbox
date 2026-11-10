# dumpbox

Despeje texto solto, a IA cataloga. Notas viram itens com tipo, contexto, prazo e prioridade. Roda 100% local (Ollama no PC), sem nuvem.

> Status: classificador + avaliação (fase 0) e **API + PWA com login** (fase 2) prontos. Falta: bot Telegram, modo demo, imagem.

## Como funciona

```
PWA no celular (fila offline) --Tailscale/HTTPS--> FastAPI no PC --> worker + Ollama --> SQLite
Telegram bot (lembretes/captura) ------------------> mesma fila
```

- **Tudo roda no seu PC** (Ollama + FastAPI + SQLite). O celular só abre a PWA, via Tailscale (URL privada), com login próprio.
- **Offline-first no navegador:** notas ficam numa fila local com UUID e são enviadas quando o servidor volta (idempotente).
- **Nunca perde nota:** se a IA falha, a captura fica em "Revisar" com o texto original.
- **A IA não calcula datas.** O modelo copia o trecho (`prazo_texto`); um parser determinístico em pt-BR resolve a data e a prioridade.
- Saída do modelo forçada por JSON Schema (gerado do Pydantic).

## Avaliação

```bash
ollama pull qwen2.5:1.5b
python eval/run_eval.py qwen2.5:1.5b            # dataset sintético público
python eval/run_eval.py qwen2.5:1.5b data/private/casos.jsonl   # suas notas reais (não vai pro git)
python tests/test_rules.py                      # regras de data
```

Métricas: JSON válido, acerto do nº de itens (split), tipo, contexto, prazo, latência p50.

### Resultados

| modelo | json válido | split | tipo | contexto | prazo | p50 |
|---|---|---|---|---|---|---|
| qwen2.5:1.5b, prompt v1 | 100% | 93% | 73% | 29% | 80%* | 2,7 s |
| qwen2.5:1.5b, prompt v2 | 100% | 93% | 53% | 73% | 87% | 2,4 s |
| **qwen2.5:7b, prompt v2** | 100% | 98% | 96% | 89% | 98% | 3,2 s |

46 casos sintéticos, CPU (sem GPU), p50 por nota. *v1 medido antes de corrigir o parser de datas. Prompt v2 = definições fechadas + 3 exemplos fixos.

## Estrutura

```
backend/dumpbox/   schema.py (contrato), rules.py (datas/prioridade), classifier.py (Ollama)
eval/              harness de avaliação
data/public/       casos sintéticos
data/private/      notas reais (gitignored)
schema/            JSON Schema exportado
docs/              arquitetura e decisões
```

## Documentação

- [`docs/planejamento.md`](docs/planejamento.md): ideia, decisões, revisão crítica
- [`docs/arquitetura.md`](docs/arquitetura.md): decisões finais, modelo de dados, fases
- [`docs/visao-imagem.md`](docs/visao-imagem.md): entrada por imagem (checklist)
- [`docs/ambiente.md`](docs/ambiente.md): o que já está baixado e o que falta instalar

## Privacidade

Repo público: nenhuma nota real. `data/private/`, `.env` e modelos `.gguf` ficam no `.gitignore`. Pesos dos modelos têm licença própria (ex.: Qwen2.5-1.5B é Apache 2.0); não são redistribuídos aqui.

