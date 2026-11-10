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
$env:DUMPBOX_PASSWORD_HASH = python -m dumpbox.auth "sua senha"   # com PYTHONPATH=backend
$env:DUMPBOX_SECRET = "<hex aleatório>"      # mantém a sessão após reiniciar
$env:OLLAMA_MODELS = "D:\Ollama\models"; D:\Ollama\ollama.exe serve
uvicorn dumpbox.api:app --app-dir backend --host 127.0.0.1 --port 8000
tailscale serve --bg 8000                    # depois de instalar o Tailscale
```

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
