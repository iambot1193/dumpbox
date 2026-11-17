"""Cópia do banco para o celular (modo celular → "Importar cópia do PC"). Só lê: abre o SQLite em modo leitura.

    PYTHONPATH=backend python -m dumpbox.exportar [arquivo.json]     (banco: DUMPBOX_HOME, como o servidor)
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from . import config
from .db import DB_PATH


def copia(caminho: Path = DB_PATH) -> dict:
    c = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    campos = ("id", "tipo", "titulo", "contexto", "prazo_em", "prioridade", "estado", "criado_em",
              "grade_col", "grade_lin", "grade_larg", "grade_alt", "repete")
    itens = [{k: r[k] for k in campos if k in r.keys()} for r in c.execute("SELECT * FROM item WHERE estado!='arquivado'")]
    pastas = [dict(r) for r in c.execute("SELECT slug, nome, descricao FROM pasta ORDER BY ordem, criado_em")]
    c.close()
    return {"dumpbox": 1, "exportado_em": datetime.now().isoformat(timespec="seconds"), "itens": itens, "pastas": pastas}


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else config.HOME / f"copia-celular-{datetime.now():%Y-%m-%d}.json"
    d = copia()
    destino.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print(f"{len(d['itens'])} itens, {len(d['pastas'])} pastas -> {destino}")
