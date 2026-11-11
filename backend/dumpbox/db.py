"""SQLite do servidor (fonte da verdade). Texto original só muda em "Apagar de vez"; itens são derivados."""
import json
import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from . import config

DB_PATH = Path(os.getenv("DUMPBOX_DB", config.HOME / "dumpbox.db"))
_MIGRA = threading.Lock()  # worker e requests conectam ao mesmo tempo na subida

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
CREATE TABLE IF NOT EXISTS pasta(  -- pastas = contexto do item; o usuário cria e apaga
  slug TEXT PRIMARY KEY, nome TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '', ordem INTEGER NOT NULL, criado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imagem(  -- foto esperando a IA; apagada depois que vira itens
  captura_id TEXT PRIMARY KEY REFERENCES captura(id), dados TEXT NOT NULL, instrucao TEXT);
"""
PADRAO = [  # descrição vai para o prompt: diz à IA o que entra em cada pasta
    ("casa", "Casa", "dia a dia, pessoal, coisas de casa"),
    ("trabalho", "Trabalho", "emprego: time, gestor, relatório, sistemas da empresa"),
    ("freelance", "Freelance", "cliente próprio por fora, proposta, domínio"),
    ("estudos", "Estudos", "faculdade, AVA, artigo, prova, curso, TCC"),
    ("saude", "Saúde", "médico, exame, treino"),
    ("financas", "Finanças", "pagar, boleto, banco, imposto, investir"),
    ("outro", "Outro", "ideias soltas e o que não cabe nas outras"),
]
FIXA = "outro"  # não pode ser apagada: é para onde vai item sem pasta
RESERVADO = {"hoje", "revisar", "lixeira"}  # nomes das telas fixas
MAX_PASTAS = 30
PASTAS: list[dict] = []  # cache em memória (1 processo): o detector de instruções roda sem conexão


def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    with _MIGRA:
        if "grade_col" not in {r["name"] for r in c.execute("PRAGMA table_info(item)")}:  # posição/tamanho do card na pasta
            for col in ("grade_col", "grade_lin", "grade_larg", "grade_alt"):
                c.execute(f"ALTER TABLE item ADD COLUMN {col} INTEGER")
            c.commit()
        if "instrucao" not in {r["name"] for r in c.execute("PRAGMA table_info(imagem)")}:  # texto escrito junto com a foto
            c.execute("ALTER TABLE imagem ADD COLUMN instrucao TEXT")
            c.commit()
        if not c.execute("SELECT 1 FROM pasta LIMIT 1").fetchone():
            c.executemany("INSERT INTO pasta(slug,nome,descricao,ordem,criado_em) VALUES(?,?,?,?,?)",
                          [(s, n, d, i, agora()) for i, (s, n, d) in enumerate(PADRAO)])
            c.commit()
    pastas(c)
    return c


def pastas(c: sqlite3.Connection) -> list[dict]:
    rows = [dict(r) for r in c.execute("SELECT slug, nome, descricao FROM pasta ORDER BY ordem, criado_em")]
    PASTAS[:] = rows
    return rows


def slug_de(valor: str | None) -> str | None:
    """'Saúde', 'saude' ou 'projetos_pessoais' -> slug da pasta; None se não existe."""
    n = normalizar(valor or "")
    return next((p["slug"] for p in PASTAS if n and n in (normalizar(p["slug"]), normalizar(p["nome"]))), None)


def nome_pasta(slug: str) -> str:
    return next((p["nome"] for p in PASTAS if p["slug"] == slug), slug)


def texto_pastas() -> str:
    return "PASTAS (contexto) que existem; use só estes slugs:\n" + "\n".join(
        f"- {p['slug']}: {p['nome']}" + (f" ({p['descricao']})" if p["descricao"] else "") for p in PASTAS)


def criar_pasta(c: sqlite3.Connection, nome: str, descricao: str = "") -> str:
    nome = " ".join(nome.split())[:40]
    slug = normalizar(nome).replace(" ", "_")[:40]
    pastas(c)
    if not slug:
        raise ValueError("dê um nome com letras ou números")
    if slug in RESERVADO:
        raise ValueError(f"“{nome}” é o nome de uma tela do app; escolha outro")
    if slug_de(nome) or any(p["slug"] == slug for p in PASTAS):
        raise ValueError(f"já existe a pasta “{nome_pasta(slug_de(nome) or slug)}”")
    if len(PASTAS) >= MAX_PASTAS:
        raise ValueError(f"limite de {MAX_PASTAS} pastas")
    ordem = (c.execute("SELECT MAX(ordem) FROM pasta").fetchone()[0] or 0) + 1
    c.execute("INSERT INTO pasta(slug,nome,descricao,ordem,criado_em) VALUES(?,?,?,?,?)", (slug, nome, descricao[:200], ordem, agora()))
    c.commit()
    pastas(c)
    return slug


def remover_pasta(c: sqlite3.Connection, slug: str) -> None:
    """Só a pasta; quem chama já tirou os itens dela (com diário)."""
    c.execute("DELETE FROM pasta WHERE slug=? AND slug!=?", (slug, FIXA))
    c.commit()
    pastas(c)


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def nova_captura(c: sqlite3.Connection, id_: str, texto: str, origem: str = "web", criado_em: str | None = None) -> bool:
    """Idempotente: mesmo id (UUID gerado no cliente) não duplica. True se era nova.
    `criado_em`: hora em que o cliente escreveu (fila offline); padrão = agora."""
    cur = c.execute("INSERT OR IGNORE INTO captura(id,texto,origem,criado_em) VALUES(?,?,?,?)", (id_, texto, origem, criado_em or agora()))
    c.commit()
    return cur.rowcount == 1


def apagar_de_vez(c: sqlite3.Connection, ids: list[int]) -> int:
    """Apaga da Lixeira sem volta: item, diário e o texto dele. Só vale para item já arquivado."""
    n = 0
    for i in ids:
        row = c.execute("SELECT captura_id FROM item WHERE id=? AND estado='arquivado'", (i,)).fetchone()
        if row is None:
            continue
        c.execute("DELETE FROM item WHERE id=?", (i,))
        c.execute("DELETE FROM alteracao WHERE item_id=?", (i,))
        resto = [r["titulo"] or "" for r in c.execute("SELECT titulo FROM item WHERE captura_id=?", (row["captura_id"],))]
        if resto:  # a nota original misturava outros itens: reescreve sem o apagado para o texto dele não ficar guardado
            c.execute("UPDATE captura SET texto=? WHERE id=?", ("\n".join(resto), row["captura_id"]))
        else:
            c.execute("DELETE FROM classificacao WHERE captura_id=?", (row["captura_id"],))
            c.execute("DELETE FROM captura WHERE id=?", (row["captura_id"],))
        n += 1
    c.commit()
    return n


def normalizar(s: str) -> str:
    """Compara títulos sem acento, caixa e pontuação: 'Fazer Claude críticas' == 'fazer claude criticas'."""
    s = "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def exemplos(c: sqlite3.Connection, limite: int = 40) -> str:
    """Como o usuário organiza: itens que mudaram de pasta e continuam lá (arraste, Mover, instrução, IA).
    Vai para o prompt como exemplo; mover de novo corrige o exemplo.
    ponytail: mudança automática que o usuário não corrigiu também vira exemplo; separar por origem se reforçar erro."""
    rows = c.execute(
        "SELECT i.titulo, i.contexto FROM alteracao a JOIN item i ON i.id=a.item_id "
        "WHERE a.campo='contexto' AND a.desfeito=0 AND i.contexto=a.depois AND i.estado!='arquivado' "
        "GROUP BY i.id ORDER BY MAX(a.id) DESC LIMIT ?", (limite,)).fetchall()
    if not rows:
        return ""
    return "Como este usuário organiza (título -> contexto). Siga isso para itens parecidos:\n" + "\n".join(
        f"- {str(r['titulo']).replace(chr(10), ' ')} -> {r['contexto']}" for r in rows)


def salvar_resultado(c: sqlite3.Connection, captura_id: str, r) -> None:
    c.execute(
        "INSERT INTO classificacao(captura_id,modelo,prompt_v,latencia_ms,valido,erro,criado_em) VALUES(?,?,?,?,?,?,?)",
        (captura_id, r.modelo, r.prompt_v, r.latencia_ms, int(r.itens is not None), r.erro, agora()),
    )
    if r.itens is None:  # nunca perder a nota: fica em 'falhou' (aba revisar)
        c.execute("UPDATE captura SET status='falhou', erro=? WHERE id=?", (r.erro, captura_id))
    else:
        abertos = {normalizar(x["titulo"] or "") for x in c.execute("SELECT titulo FROM item WHERE estado='catalogado'")}
        for i in r.itens:
            if normalizar(i.titulo) in abertos:  # já existe aberto (ou repetido na mesma nota): não duplica
                continue
            abertos.add(normalizar(i.titulo))
            c.execute(
                "INSERT INTO item(captura_id,tipo,titulo,contexto,prazo_texto,prazo_em,prioridade,tags,estado,criado_em) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (captura_id, i.tipo, i.titulo, i.contexto, i.prazo_texto, i.prazo_em, i.prioridade,
                 json.dumps(i.tags, ensure_ascii=False), i.estado, agora()),
            )
        c.execute("UPDATE captura SET status='ok', erro=NULL WHERE id=?", (captura_id,))
        c.execute("DELETE FROM imagem WHERE captura_id=?", (captura_id,))  # já virou itens: não guarda a foto
    c.commit()
