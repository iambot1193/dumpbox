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

## Usar (Windows, sem instalar nada)

1. Baixe o `dumpbox.exe` em [Releases](../../releases) e dê duplo clique.
2. Se o Windows mostrar "O Windows protegeu seu PC" (o exe não é assinado): **Mais informações → Executar assim mesmo**.
3. O navegador abre sozinho. Crie uma senha e pronto.
4. Na **primeira vez** o app baixa o motor de IA (Ollama) e o modelo, com barra de progresso na tela. Precisa de ~10 GB livres e internet. Enquanto isso você já pode guardar notas; elas são classificadas quando a IA ficar pronta.

- **Modelo escolhido pela RAM:** 16 GB ou mais usa `qwen2.5:7b`; menos que isso usa `qwen2.5:1.5b` (mais leve, bem menos preciso; veja o benchmark).
- **Dados:** `%LOCALAPPDATA%\dumpbox` (banco, senha e modelos). Para desinstalar, apague essa pasta e o exe.
- Mantenha a janela do dumpbox aberta enquanto usa; fechar encerra o app.
- Tudo roda local: nenhuma nota sai do seu PC.

## Instalação para desenvolvedores (qualquer SO, sem Tailscale)

```bash
pip install -r requirements.txt
ollama pull qwen2.5:7b                      # PC fraco: qwen2.5:1.5b (menos preciso, ver benchmark)
python run.py          # sobe o servidor, abre o navegador e prepara Ollama + modelo sozinho
# ou, com Ollama já instalado: python -m uvicorn dumpbox.api:app --app-dir backend
.\build.ps1            # gera dist\dumpbox.exe (Windows)
```

No Windows, `iniciar.ps1` sobe o Ollama e o servidor juntos (ajuste `OLLAMA_EXE`/`OLLAMA_MODELS` se não for o caminho padrão).

### Acessar de outro aparelho (opcional)
O projeto não depende de nenhum serviço de rede. Escolha o que preferir:
- **Mesma rede Wi-Fi:** `--host 0.0.0.0` e abra `http://<ip-do-pc>:8000` (HTTP, só em rede confiável).
- **Fora de casa:** VPN privada como [Tailscale](https://tailscale.com) (`tailscale serve --bg 8000` dá HTTPS) ou um túnel como Cloudflare Tunnel. Com HTTPS, defina `DUMPBOX_COOKIE_SECURE=1`.
- Nunca exponha a porta direto na internet (port-forward): o login é de usuário único e simples.

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

