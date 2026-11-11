"""Foto ou print de lista/checklist -> linhas de texto (marcadas ou não) -> classificador normal.

O modelo de visão só transcreve; tipo, pasta, data e prioridade continuam com o classificador de texto e `rules.py`.
Caixa marcada (✓ ou X) vira item já feito. Texto riscado o qwen2.5vl:3b não distingue (medido em eval/run_eval_visao.py).
"""
import os
import re
import time
import uuid
from datetime import datetime

import httpx
from pydantic import BaseModel, Field

from . import chat
from .classifier import OLLAMA_URL, Resultado, classificar

MODELO = os.getenv("DUMPBOX_MODELO_VISAO", "qwen2.5vl:3b")


class Linha(BaseModel):
    texto: str = Field(max_length=200)
    marcado: bool = False


PEDIDO = """Olhe a imagem com atenção.
1) Liste todos os itens da lista, um por linha.
2) Depois de cada item, escreva " => vazia" se a caixa está vazia ou não há caixa e o texto não está riscado; " => marcada" se a caixa tem ✓ ou X, ou o texto tem uma linha atravessando.
Não escreva o título."""
# ponytail: texto livre, não JSON Schema: com schema o qwen2.5vl:3b devolve lista vazia (medido)
_LINHA = re.compile(r"^\s*(?:\d+[.)]|[-*•])?\s*(.+?)\s*=>\s*(marcad|vazi)", re.I)


def ler_resposta(txt: str) -> list[Linha]:
    linhas = []
    for bruta in txt.splitlines():
        m = _LINHA.match(bruta)
        if m and m[1].strip():
            linhas.append(Linha(texto=m[1].strip()[:200], marcado=m[2].lower() == "marcad"))
    if not linhas:  # às vezes o modelo lista sem as setas: vale como lista sem marcas
        brutas = [re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", b).strip() for b in txt.splitlines() if b.strip()]
        if len(brutas) > 2 and len(brutas[0].split()) <= 2:  # ponytail: 1ª linha curta = título; heurística
            brutas = brutas[1:]
        linhas = [Linha(texto=b[:200]) for b in brutas]
    if len(linhas) > 2 and all(l.marcado for l in linhas):  # tudo "marcado" = o modelo não viu as marcas; não fecha nada sozinho
        for l in linhas:
            l.marcado = False
    return linhas[:60]


def transcrever(imagem_b64: str, modelo: str = MODELO) -> list[Linha]:
    """Levanta RuntimeError com mensagem para o usuário se o modelo falhar."""
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=600, json={
            "model": modelo, "stream": False, "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1500},
            "messages": [{"role": "user", "content": PEDIDO, "images": [imagem_b64]}]})
        if r.status_code == 404:
            raise RuntimeError(f"modelo de visão {modelo} ainda não foi baixado")
        r.raise_for_status()
        return ler_resposta(r.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise RuntimeError(f"{type(e).__name__}: {e}"[:200]) from e


def texto_de(linhas: list[Linha]) -> str:
    """Como a imagem fica guardada na captura (o que aparece em Revisar e em 'Apagar de vez')."""
    return "\n".join(("[x] " if l.marcado else "") + l.texto.strip() for l in linhas)


def existente(linha: str, itens: list) -> int | None:
    """Id do item que a linha da foto repete (nos dois sentidos: ≥60% das palavras de um no outro), ou None."""
    batem = [it for it in itens if chat.citado(it["titulo"] or "", linha) and chat.citado(linha, it["titulo"] or "")]
    batem.sort(key=lambda it: it["estado"] != "catalogado")  # aberto primeiro: é esse que a marca fecha
    return batem[0]["id"] if batem else None


def processar(imagem_b64: str, agora: datetime, base: datetime, modelo_texto: str, instrucao: str = "",
              c=None, captura_id: str | None = None, **kw) -> tuple[str | None, Resultado]:
    """Devolve (transcrição, resultado). Marcadas e não marcadas vão separadas ao classificador.
    `instrucao`: o que o usuário escreveu junto com a foto ("tudo do trabalho, pra sexta"); vai para o classificador.
    Com `c`: linha que já é um item não vira item novo; se está marcada, fecha o item (diário, com Desfazer)."""
    t0 = time.perf_counter()
    try:
        linhas = transcrever(imagem_b64)
    except RuntimeError as e:
        return None, Resultado(None, MODELO, "visao", int((time.perf_counter() - t0) * 1000), str(e))
    if not linhas:
        return "", Resultado(None, MODELO, "visao", int((time.perf_counter() - t0) * 1000), "nenhum item encontrado na imagem")
    novas = linhas
    if c is not None:
        abertos = [dict(r) for r in c.execute("SELECT id, titulo, estado FROM item WHERE estado!='arquivado' ORDER BY id DESC")]
        grupo, novas = str(uuid.uuid4()), []
        for l in linhas:
            iid = existente(l.texto, abertos)
            if iid is None:
                novas.append(l)
            elif l.marcado:  # já feito: _mudar não grava nada
                chat.aplicar(c, chat.Acao(tipo="estado", item_id=iid, valor="feito"), grupo, captura_id)
    itens = []
    for marcado in (False, True):
        parte = [l.texto for l in novas if l.marcado == marcado]
        if not parte:
            continue
        r = classificar("\n".join(parte), agora, modelo_texto, base=base, instrucao=instrucao, **kw)
        if r.itens is None:  # nada se perde: a transcrição fica em Revisar
            r.latencia_ms = int((time.perf_counter() - t0) * 1000)
            return texto_de(linhas), r
        for it in r.itens:
            it.estado = "feito" if marcado else "catalogado"
        itens += r.itens
    return texto_de(linhas), Resultado(itens, f"{MODELO}+{modelo_texto}", "visao", int((time.perf_counter() - t0) * 1000))


if __name__ == "__main__":  # autoteste do leitor da resposta (sem modelo)
    ls = ler_resposta("1. Arroz => marcada\n2. Feijão => vazia\n- Café => Marcada\nlixo sem seta")
    assert [(l.texto, l.marcado) for l in ls] == [("Arroz", True), ("Feijão", False), ("Café", True)]
    assert not any(l.marcado for l in ler_resposta("a => marcada\nb => marcada\nc => marcada"))
    assert [l.texto for l in ler_resposta("Viagem\nComprar passagem\nReservar hotel")] == ["Comprar passagem", "Reservar hotel"]
    print("ok")
