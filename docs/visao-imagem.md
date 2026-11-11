# Entrada por imagem

> **Feito (11/11/2026): fluxo A** em `backend/dumpbox/visao.py` (`POST /api/capturas/imagem`, botão de câmera na PWA), modelo `qwen2.5vl:3b`, avaliação em `eval/run_eval_visao.py` (resultados no README). Diferente do plano abaixo: o modelo devolve texto `item => marcada/vazia`, não JSON (com schema o 3B devolvia lista vazia), e item marcado entra como `feito` direto (reversível com Reabrir); só a lista inteira marcada é tratada como erro do modelo. Fluxo B continua ideia.

Pedido: subir uma imagem e dizer "classifique quais já foram feitos, de acordo com os itens do checklist".

**Viável.** Dois fluxos diferentes:

## A. Foto de um checklist (papel/print) → itens + estado
A imagem *é* o checklist. Extrair cada linha e se está marcada.
- Texto impresso/print: OCR (Tesseract, PaddleOCR) + LLM de texto estrutura. Rápido e barato.
- Manuscrito ou caixas ☑/☐: modelo de visão (VLM).

## B. Checklist existente + imagem como evidência
Itens já estão no banco. A imagem (print, foto) mostra o progresso. Pergunta ao VLM: "para cada item, a imagem mostra que foi feito?". Saída por item: `feito | pendente | incerto` + confiança + trecho que justifica.

## Modelos de visão locais (Ollama)
`qwen2.5vl:3b`/`7b`, `gemma3:4b`/`12b`, `llama3.2-vision:11b`, `minicpm-v:8b`. Este PC: 24 GB RAM, sem GPU NVIDIA detectada, então CPU. Esperar 3B-7B lento (dezenas de segundos a minutos por imagem). Aceitável no fluxo assíncrono.

## Cuidados
- VLM pequeno erra marca de checkbox e letra manuscrita. Tudo com confiança baixa ou `incerto` vai para a aba "revisar"; nunca marcar como feito sozinho.
- Reduzir a imagem (ex.: lado maior 1280 px) antes: menos tokens visuais, mais rápido.
- Mesmo contrato JSON validado por schema (`itens[{id, estado, confianca, evidencia}]`).
- Dataset de avaliação próprio: 30+ imagens sintéticas com gabarito.
- Privacidade: imagens reais ficam em `data/private/`, fora do git.

## Onde entra
Fase 5, depois do classificador de texto estar medido. O app Android só precisa enviar a imagem (share sheet / câmera) para o PC.
