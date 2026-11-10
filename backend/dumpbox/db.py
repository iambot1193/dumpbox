"""SQLite do servidor (fonte da verdade). Texto original nunca é alterado; itens são derivados."""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config

DB_PATH = Path(os.getenv("DUMPBOX_DB", config.HOME / "dumpbox.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS captura(
  id TEXT PRIMARY KEY, texto TEXT NOT NULL, origem TEXT NOT NULL DEFAULT 'web',
  criado_em TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pendente', erro TEXT);
CREATE TABLE IF NOT EXISTS item(
  id INTEGER PRIMARY KEY AUTOINCREMENT, captura_id TEXT NOT NULL REFERENCES captura(id),
  tipo TEXT, titulo TEXT, contexto TEXT, prazo_texto TEXT, prazo_em TEXT, prioridade TEXT,
  tags TEXT, estado TEXT NOT NULL DEFAULT 'catalogado', criado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS classificacao(
  id INTEGER PRIMARY KEY AUTOINCREMENT, captura_id TEXT NOT NULL, modelo TEXT, prompt_v TEXT,
  latencia_ms INTEGER, valido INTEGER, erro TEXT, criado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alteracao(  -- diário de edições automáticas: base do "Desfazer"
  id INTEGER PRIMARY KEY AUTOINCREMENT, grupo TEXT NOT NULL, captura_id TEXT, item_id INTEGER NOT NULL,
  campo TEXT NOT NULL, antes TEXT, depois TEXT, descricao TEXT, criado_em TEXT NOT NULL,
  desfeito INTEGER NOT NULL DEFAULT 0);
"""


def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def nova_captura(c: sqlite3.Connection, id_: str, texto: str, origem: str = "web") -> bool:
    """Idempotente: mesmo id (UUID gerado no cliente) não duplica. True se era nova."""
    cur = c.execute("INSERT OR IGNORE INTO captura(id,texto,origem,criado_em) VALUES(?,?,?,?)", (id_, texto, origem, agora()))
    c.commit()
    return cur.rowcount == 1


def salvar_resultado(c: sqlite3.Connection, captura_id: str, r) -> None:
    c.execute(
        "INSERT INTO classificacao(captura_id,modelo,prompt_v,latencia_ms,valido,erro,criado_em) VALUES(?,?,?,?,?,?,?)",
        (captura_id, r.modelo, r.prompt_v, r.latencia_ms, int(r.itens is not None), r.erro, agora()),
    )
    if r.itens is None:  # nunca perder a nota: fica em 'falhou' (aba revisar)
        c.execute("UPDATE captura SET status='falhou', erro=? WHERE id=?", (r.erro, captura_id))
    else:
        for i in r.itens:
            c.execute(
                "INSERT INTO item(captura_id,tipo,titulo,contexto,prazo_texto,prazo_em,prioridade,tags,criado_em) VALUES(?,?,?,?,?,?,?,?,?)",
                (captura_id, i.tipo, i.titulo, i.contexto, i.prazo_texto, i.prazo_em, i.prioridade,
                 json.dumps(i.tags, ensure_ascii=False), agora()),
            )
        c.execute("UPDATE captura SET status='ok', erro=NULL WHERE id=?", (captura_id,))
    c.commit()
