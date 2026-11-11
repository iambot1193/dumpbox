"""Texto solto -> itens catalogados. Ollama com JSON Schema + regras determinísticas."""
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from pydantic import ValidationError

from .rules import prioridade, resolver_prazo
from typing import get_args

from .schema import Contexto, Item, SaidaIA

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
- contexto: saude (médico, exame, treino), financas (pagar, boleto, banco, imposto, fatura), estudos (curso, prova, estudar, faculdade, AVA, artigo, TCC), freelance (cliente, proposta, portal, domínio), trabalho (time, gestor, relatório, pull request), casa (resto do dia a dia), outro (ideias soltas).
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


def finalizar(itens_ia, agora: datetime, base: datetime | None = None, texto: str | None = None) -> list[Item]:
    """ItemIA (saída do modelo) -> Item: data e prioridade por regra, nunca pela IA.
    `base` = quando o texto foi escrito ("amanhã" numa mensagem antiga conta a partir dela).
    `texto` = nota original: com um item só, se o trecho do modelo não vira data (ele corta "dia 4" em "4"
    ou esquece "hoje"), a regra lê a nota inteira. Nota (tipo) é informação: nunca tem prazo."""
    itens = []
    for i in itens_ia:
        prazo = resolver_prazo(i.prazo_texto, base or agora)
        if prazo is None and texto and len(itens_ia) == 1:
            prazo = resolver_prazo(texto, base or agora)
        if i.tipo == "nota":  # "nota: as férias começam dia 22" não é tarefa com prazo
            prazo = None
        itens.append(Item(**i.model_dump(), prazo_em=prazo, prioridade=prioridade(prazo, i.titulo, agora)))
    return itens


# cabeçalho de mensagem copiada do WhatsApp: "[07:43, 30/10/2026] Nome: texto"
# ponytail: só o formato de copiar no app; o .txt exportado ("30/10/2026 07:43 - Nome:") entra se aparecer
_ZAP = re.compile(r"^\[(\d{1,2}):(\d{2}), (\d{1,2})/(\d{1,2})/(\d{4})\] [^:\n]{1,40}: ?", re.M)


def blocos_zap(texto: str) -> list[tuple[datetime | None, str]]:
    """Separa a colagem por mensagem, sem o cabeçalho, com a data de cada uma. Sem cabeçalho: [(None, texto)]."""
    ms = list(_ZAP.finditer(texto))
    if not ms:
        return [(None, texto)]
    blocos = [(None, texto[:ms[0].start()])] if texto[:ms[0].start()].strip() else []
    for n, m in enumerate(ms):
        h, mi, d, mo, a = map(int, m.groups())
        try:
            quando = datetime(a, mo, d, h, mi)
        except ValueError:
            quando = None
        blocos.append((quando, texto[m.end():ms[n + 1].start() if n + 1 < len(ms) else len(texto)]))
    return blocos


def classificar(texto: str, agora: datetime, modelo: str = "qwen2.5:1.5b", tentativas: int = 2,
                exemplos: str = "", pastas: list[dict] | None = None, base: datetime | None = None,
                instrucao: str = "") -> Resultado:
    """`pastas`: as do usuário ({slug, nome, descricao}); sem elas, as padrão (benchmark).
    `base`: quando o texto foi escrito (nota feita offline); "amanhã" conta a partir dela."""
    blocos = blocos_zap(texto)
    if blocos[0][0] is None and len(blocos) == 1:
        return _classificar(texto, agora, base, modelo, tentativas, exemplos, pastas, instrucao)
    t0, itens = time.perf_counter(), []
    for quando, parte in blocos:
        if not parte.strip():
            continue
        r = _classificar(parte, agora, quando or base, modelo, tentativas, exemplos, pastas, instrucao)
        if r.itens is None:  # uma mensagem falhou: a colagem inteira vai para Revisar (nada se perde)
            r.latencia_ms = int((time.perf_counter() - t0) * 1000)
            return r
        itens += r.itens
    return Resultado(itens, modelo, PROMPT_V, int((time.perf_counter() - t0) * 1000))


def schema_com_pastas(slugs: list[str]) -> dict:
    """JSON Schema da saída com o enum das pastas que existem agora (o modelo não inventa pasta)."""
    s = SaidaIA.model_json_schema()
    s["$defs"]["ItemIA"]["properties"]["contexto"] = {"type": "string", "enum": slugs}
    return s


def _classificar(texto: str, agora: datetime, base: datetime | None, modelo: str, tentativas: int, exemplos: str,
                 pastas: list[dict] | None, instrucao: str = "") -> Resultado:
    t0, erro = time.perf_counter(), None
    slugs = [p["slug"] for p in pastas] if pastas else list(get_args(Contexto))
    sistema = SISTEMA + (f"\n{exemplos}" if exemplos else "")
    if instrucao:  # texto escrito junto com a foto: orienta tipo/pasta/prazo, não vira item
        sistema += f"\nO usuário escreveu isto sobre a lista abaixo; siga para tipo, pasta e prazo, sem criar item para ela: {instrucao}"
    if pastas:
        sistema += "\nPastas do usuário (contexto); use SÓ estes slugs:\n" + "\n".join(
            f"- {p['slug']}: {p['nome']}" + (f" ({p['descricao']})" if p.get("descricao") else "") for p in pastas)
    # saída ~150 tokens por linha (um item cada): teto fixo cortava o JSON de colagens longas
    orcamento = min(3000, max(400, 150 * (texto.count("\n") + 1)))
    for tentativa in range(tentativas):
        try:
            r = httpx.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": modelo,
                    "stream": False,
                    "format": schema_com_pastas(slugs),
                    "options": {"temperature": 0, "num_ctx": 8192,
                                "num_predict": min(4500, orcamento * (tentativa + 1))},  # retry com o dobro
                    "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": texto}],
                },
                timeout=120,
            )
            r.raise_for_status()
            saida = SaidaIA.model_validate_json(r.json()["message"]["content"])
            for i in saida.itens:  # fora do enum (modelo sem suporte a schema): cai em "outro"
                if i.contexto not in slugs:
                    i.contexto = "outro" if "outro" in slugs else slugs[0]
            return Resultado(finalizar(saida.itens, agora, base, texto), modelo, PROMPT_V, int((time.perf_counter() - t0) * 1000))
        except (httpx.HTTPError, ValidationError, KeyError, ValueError) as e:
            erro = f"{type(e).__name__}: {e}"[:200]
    # nunca perder a nota: quem chamar manda o texto cru pra "revisar"
    return Resultado(None, modelo, PROMPT_V, int((time.perf_counter() - t0) * 1000), erro)
