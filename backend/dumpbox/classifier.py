"""Texto solto -> itens catalogados. Ollama com JSON Schema + regras determinísticas."""
import os
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from pydantic import ValidationError

from .rules import prioridade, resolver_prazo
from .schema import Item, SaidaIA

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
PROMPT_V = os.getenv("DUMPBOX_PROMPT", "v2")
_V1 = (
    "Você cataloga anotações soltas em português. Separe em itens independentes. "
    "tipo: tarefa, compromisso (tem hora/data marcada), ideia, compra ou nota. "
    "contexto: casa, trabalho, freelance, estudos, saude, financas ou outro. "
    "titulo: curto, começa com verbo quando for tarefa. "
    "prazo_texto: copie literalmente o trecho de data/hora do texto, senão null. Não calcule datas."
)
# v2: definições mais fechadas + few-shot fixo (prefixo constante = cacheável)
_V2 = _V1 + """
Regras:
- compromisso: evento com hora ou lugar marcado (reunião, consulta, prova, treino). Fazer algo até uma data é tarefa.
- compra: lista do que comprar. nota: informação para guardar, sem ação. ideia: começa com "ideia".
- contexto: saude (médico, exame, treino), financas (pagar, boleto, banco, imposto, fatura), estudos (curso, prova, estudar), freelance (cliente, proposta, portal, domínio), trabalho (time, gestor, relatório, pull request), casa (resto do dia a dia), outro (ideias soltas).
- Um item por ação. "pagar X amanhã e comprar Y sábado" são 2 itens; "comprar A e B" é 1 item.
Exemplos:
"pagar boleto dia 20" -> {"itens":[{"tipo":"tarefa","titulo":"Pagar boleto","contexto":"financas","prazo_texto":"dia 20","tags":[]}]}
"dentista sexta 14h e comprar pão" -> {"itens":[{"tipo":"compromisso","titulo":"Dentista","contexto":"saude","prazo_texto":"sexta 14h","tags":[]},{"tipo":"compra","titulo":"Comprar pão","contexto":"casa","prazo_texto":null,"tags":[]}]}
"nota: cliente prefere meet" -> {"itens":[{"tipo":"nota","titulo":"Cliente prefere meet","contexto":"freelance","prazo_texto":null,"tags":[]}]}"""
SISTEMA = _V1 if PROMPT_V == "v1" else _V2


@dataclass
class Resultado:
    itens: list[Item] | None
    modelo: str
    prompt_v: str
    latencia_ms: int
    erro: str | None = None


def classificar(texto: str, agora: datetime, modelo: str = "qwen2.5:1.5b", tentativas: int = 2) -> Resultado:
    t0, erro = time.perf_counter(), None
    # saída ~150 tokens por linha (um item cada): teto fixo cortava o JSON de colagens longas
    orcamento = min(3000, max(400, 150 * (texto.count("\n") + 1)))
    for tentativa in range(tentativas):
        try:
            r = httpx.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": modelo,
                    "stream": False,
                    "format": SaidaIA.model_json_schema(),
                    "options": {"temperature": 0, "num_ctx": 8192,
                                "num_predict": min(4500, orcamento * (tentativa + 1))},  # retry com o dobro
                    "messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": texto}],
                },
                timeout=120,
            )
            r.raise_for_status()
            saida = SaidaIA.model_validate_json(r.json()["message"]["content"])
            itens = []
            for i in saida.itens:
                prazo = resolver_prazo(i.prazo_texto, agora)
                itens.append(Item(**i.model_dump(), prazo_em=prazo, prioridade=prioridade(prazo, i.titulo, agora)))
            return Resultado(itens, modelo, PROMPT_V, int((time.perf_counter() - t0) * 1000))
        except (httpx.HTTPError, ValidationError, KeyError, ValueError) as e:
            erro = f"{type(e).__name__}: {e}"[:200]
    # nunca perder a nota: quem chamar manda o texto cru pra "revisar"
    return Resultado(None, modelo, PROMPT_V, int((time.perf_counter() - t0) * 1000), erro)
