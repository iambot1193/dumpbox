"""Busca nas notas para o chat (RAG local): palavras exatas + similaridade de embedding (paraphrase-multilingual no Ollama, ~560 MB).
Vetores no próprio SQLite (tabela embedding). Sem o modelo de embedding, cai só para as palavras: o chat nunca quebra.
ponytail: força bruta em Python (ms até ~10 mil itens); trocar por sqlite-vec se passar de ~50 mil."""
import hashlib
import math
import os
import re
from array import array

import httpx

from . import db
from .classifier import OLLAMA_URL

MODELO = os.getenv("DUMPBOX_EMBED", "paraphrase-multilingual")  # nomic-embed-text: 73% em português, este 100% (eval)


def _texto(r) -> str:
    return f"{r['titulo'] or ''}\n{r['detalhe'] or ''}".strip()


def _hash(t: str) -> str:
    return hashlib.sha1(t.encode()).hexdigest()[:16]


def embed(textos: list[str], tipo: str) -> list[list[float]]:
    """tipo: 'search_document' ou 'search_query' (prefixos que o nomic-embed-text espera)."""
    r = httpx.post(f"{OLLAMA_URL}/api/embed", timeout=60, json={"model": MODELO, "input": [f"{tipo}: {t}" if "nomic" in MODELO else t for t in textos]})
    r.raise_for_status()
    return r.json()["embeddings"]


def indexar(c, limite: int = 200) -> int:
    """Gera vetor de itens novos ou com título/detalhe mudados. Devolve quantos indexou (0 = em dia)."""
    falta = [r for r in c.execute("SELECT i.id, i.titulo, i.detalhe, e.texto_hash FROM item i LEFT JOIN embedding e ON e.item_id=i.id "
                                  "WHERE i.estado!='arquivado'")
             if r["texto_hash"] != _hash(_texto(r))][:limite]
    if not falta:
        return 0
    vetores = embed([_texto(r) for r in falta], "search_document")
    c.executemany("INSERT OR REPLACE INTO embedding(item_id, modelo, vetor, texto_hash) VALUES(?,?,?,?)",
                  [(r["id"], MODELO, array("f", v).tobytes(), _hash(_texto(r))) for r, v in zip(falta, vetores)])
    c.commit()
    return len(falta)


def _cos(a, b) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


_PARADA = {"que", "qual", "quais", "sobre", "para", "pra", "com", "uma", "das", "dos", "tem", "tenho", "anotei", "minha", "meu",
           "minhas", "meus", "onde", "quando", "como", "isso", "essa", "esse", "nota", "notas", "item", "itens"}


def buscar(c, consulta: str, n: int = 8) -> list[int]:
    """Ids mais relevantes: 0.7 * cosseno + 0.3 * fração das palavras da consulta presentes no texto (pega nomes e números)."""
    rows = c.execute("SELECT i.id, i.titulo, i.detalhe, e.vetor FROM item i LEFT JOIN embedding e ON e.item_id=i.id "
                     "WHERE i.estado!='arquivado'").fetchall()
    termos = [t for t in re.findall(r"[a-z0-9]{3,}", db.normalizar(consulta)) if t not in _PARADA]
    try:
        q = embed([consulta], "search_query")[0]
    except (httpx.HTTPError, KeyError, IndexError):
        q = None  # sem modelo de embedding: só palavras
    nota = []
    for r in rows:
        txt = db.normalizar(_texto(r))
        pal = sum(t in txt for t in termos) / len(termos) if termos else 0.0
        sem = _cos(q, array("f", r["vetor"])) if q and r["vetor"] else 0.0
        s = 0.7 * sem + 0.3 * pal if q else pal
        if s > 0:
            nota.append((s, r["id"]))
    return [i for _, i in sorted(nota, reverse=True)[:n]]
