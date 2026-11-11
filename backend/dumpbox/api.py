"""API + PWA. Rodar: uvicorn dumpbox.api:app --host 127.0.0.1 --port 8000 (expor só via Tailscale)."""
import base64
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, chat, classifier, db, editor, ollama_mgr, rules, setup, visao
from .schema import Tipo

# no exe (PyInstaller) os arquivos da web ficam em sys._MEIPASS
WEB = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "web"


def processar_pendentes(c) -> int:
    """Classifica capturas pendentes, uma por vez. Retorna quantas processou."""
    n = 0
    for row in c.execute("SELECT id, texto, erro, criado_em, origem FROM captura WHERE status='pendente' ORDER BY criado_em").fetchall():
        base = datetime.fromisoformat(row["criado_em"])  # hora em que foi escrita: nota que esperou na fila não ganha prazo adiado
        img = c.execute("SELECT dados, instrucao FROM imagem WHERE captura_id=?", (row["id"],)).fetchone() if row["origem"] == "imagem" else None
        if img:  # foto: o modelo de visão transcreve, o classificador de texto cataloga
            texto, r = visao.processar(img["dados"], datetime.now(), base, ollama_mgr.modelo(), img["instrucao"] or "",
                                       c=c, captura_id=row["id"], exemplos=db.exemplos(c), pastas=db.pastas(c))
            if texto:  # o que aparece em Revisar: instrução + o que a IA leu
                c.execute("UPDATE captura SET texto=? WHERE id=?", ((img["instrucao"] + "\n" if img["instrucao"] else "") + texto, row["id"]))
        elif row["erro"] != "forcar_nota" and editor.parece_comando(row["texto"]):  # instrução de edição: aplica (reversível) + cria só o que for novo
            r = editor.interpretar(c, row["id"], row["texto"], datetime.now(), ollama_mgr.modelo(), base=base)
        else:
            r = classifier.classificar(row["texto"], datetime.now(), ollama_mgr.modelo(), exemplos=db.exemplos(c), pastas=db.pastas(c), base=base)
        db.salvar_resultado(c, row["id"], r)
        n += 1
    return n


def _worker(parar: threading.Event) -> None:
    c = db.conectar()
    while not parar.is_set():
        try:
            db.backup_diario(c)  # no máximo 1 por dia; barato quando já existe
            if not ollama_mgr.pronto() or not processar_pendentes(c):  # IA ainda preparando: notas ficam pendentes
                parar.wait(2)
        except Exception:  # worker nunca morre; erro de uma nota não derruba as outras
            time.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    parar = threading.Event()
    if os.getenv("DUMPBOX_AUTOPREPARO") == "1":
        ollama_mgr.iniciar_em_thread()
    if os.getenv("DUMPBOX_WORKER", "1") == "1":
        threading.Thread(target=_worker, args=(parar,), daemon=True).start()
    yield
    parar.set()


app = FastAPI(title="dumpbox", lifespan=lifespan)


def conexao():
    c = db.conectar()  # uma conexão por request (threadpool); WAL permite o worker escrever junto
    try:
        yield c
    finally:
        c.close()


def exige_login(sess: str | None = Cookie(default=None)) -> None:
    if not auth.token_valido(sess):
        raise HTTPException(401, "não autenticado")


class Login(BaseModel):
    senha: str


class NovaCaptura(BaseModel):
    id: str = Field(min_length=8, max_length=64)  # UUID gerado no cliente → idempotência
    texto: str = Field(min_length=1, max_length=5000)
    criado_em: datetime | None = None  # hora local em que foi escrita (fila offline); datas contam a partir dela


class NovaImagem(BaseModel):
    id: str = Field(min_length=8, max_length=64)
    imagem: str = Field(min_length=100, max_length=4_000_000)  # JPEG/PNG em base64, já reduzido no navegador
    texto: str = Field(default="", max_length=1000)  # instruções escritas junto com a foto
    criado_em: datetime | None = None


class Edicao(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)  # vários = seleção múltipla, um só Desfazer
    campo: Literal["estado", "contexto", "prioridade"]
    valor: str = Field(max_length=20)


class NovoItem(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    contexto: str = Field(default="outro", max_length=40)
    tipo: Tipo = "tarefa"
    prioridade: chat.Prioridade | None = None  # None = regra pelo prazo
    prazo: str | None = Field(default=None, max_length=60)  # texto livre ("sexta 14h"), resolvido por regra


class Posicao(BaseModel):
    id: int
    col: int = Field(ge=1, le=4)
    lin: int = Field(ge=1, le=1000)
    larg: int = Field(ge=1, le=4)
    alt: int = Field(ge=1, le=4)


class Layout(BaseModel):
    itens: list[Posicao] = Field(max_length=1000)


_PROXY = ("x-forwarded-for", "forwarded", "x-real-ip", "cf-connecting-ip", "tailscale-user-login")
_setup_lock = threading.Lock()


def _e_local(request: Request) -> bool:
    """Pedido vindo do próprio PC, sem proxy no meio (Tailscale serve/túneis chegam como 127.0.0.1 mas com cabeçalhos)."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1") and not any(h in request.headers for h in _PROXY)


class NovaSenha(BaseModel):
    senha: str = Field(min_length=8, max_length=200)


@app.get("/api/estado")
def estado():
    """Público e sem dados sensíveis: a tela decide entre criar senha, login e app; mostra o progresso da IA."""
    return {"configurado": bool(os.getenv("DUMPBOX_PASSWORD_HASH")), "preparo": {**ollama_mgr.ESTADO, "pronto": ollama_mgr.pronto()}}


@app.post("/api/setup")
def criar_senha(body: NovaSenha, request: Request, response: Response):
    """Primeiro uso: só vale enquanto NÃO há senha e só do próprio PC (evita que um visitante via túnel assuma o app)."""
    with _setup_lock:
        if os.getenv("DUMPBOX_PASSWORD_HASH"):
            raise HTTPException(409, "já configurado")
        if not _e_local(request):
            raise HTTPException(403, "crie a senha abrindo o app no próprio PC (http://127.0.0.1)")
        setup.salvar_senha(body.senha)
    response.set_cookie("sess", auth.novo_token(), httponly=True, samesite="strict", max_age=auth.SESSAO_S)
    return {"ok": True}


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not auth.limite_ok(ip):
        raise HTTPException(429, "muitas tentativas, espere 1 minuto")
    guardado = os.getenv("DUMPBOX_PASSWORD_HASH")
    if not guardado:
        raise HTTPException(503, "defina DUMPBOX_PASSWORD_HASH")
    if not auth.confere_senha(body.senha, guardado):
        raise HTTPException(401, "senha incorreta")
    response.set_cookie("sess", auth.novo_token(), httponly=True, samesite="strict",
                        secure=os.getenv("DUMPBOX_COOKIE_SECURE", "0") == "1", max_age=auth.SESSAO_S)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("sess")
    return {"ok": True}


@app.get("/api/sessao", dependencies=[Depends(exige_login)])
def sessao():
    return {"ok": True}


@app.post("/api/capturas", dependencies=[Depends(exige_login)])
def criar_captura(body: NovaCaptura, c=Depends(conexao)):
    return {"nova": db.nova_captura(c, body.id, body.texto.strip(), criado_em=_quando(body.criado_em))}


def _quando(criado_em: datetime | None) -> str | None:
    """Hora da escrita mandada pelo aparelho; relógio fora do razoável: usa a hora do PC (None)."""
    agora = datetime.now()
    quando = criado_em.replace(tzinfo=None) if criado_em else None
    if quando and agora - timedelta(days=365) <= quando <= agora + timedelta(minutes=5):
        return quando.isoformat(timespec="seconds")
    return None


@app.post("/api/capturas/imagem", dependencies=[Depends(exige_login)])
def criar_captura_imagem(body: NovaImagem, c=Depends(conexao)):
    """Foto de lista/checklist: entra na fila como captura; o worker transcreve e cataloga."""
    try:
        cabeca = base64.b64decode(body.imagem[:24], validate=True)
    except ValueError:
        raise HTTPException(422, "imagem inválida")
    if not cabeca.startswith((bytes([0xFF, 0xD8]), bytes([0x89]) + b"PNG")):  # JPEG ou PNG
        raise HTTPException(422, "envie JPEG ou PNG")
    quando = _quando(body.criado_em)
    instrucao = body.texto.strip()
    nova = db.nova_captura(c, body.id, "📷 foto aguardando a IA" + (f": {instrucao}" if instrucao else ""), "imagem", criado_em=quando)
    if nova:
        c.execute("INSERT INTO imagem(captura_id, dados, instrucao) VALUES(?,?,?)", (body.id, body.imagem, instrucao or None))
        c.commit()
    return {"nova": nova}


@app.get("/api/itens", dependencies=[Depends(exige_login)])
def listar_itens(c=Depends(conexao)):
    itens = [dict(r) for r in c.execute("SELECT * FROM item WHERE estado!='arquivado' ORDER BY criado_em DESC, id DESC")]
    revisar = [dict(r) for r in c.execute(
        "SELECT id,texto,status,erro FROM captura WHERE status IN ('pendente','falhou') ORDER BY criado_em DESC")]
    lixeira = [dict(r) for r in c.execute("SELECT id,titulo,contexto,tipo FROM item WHERE estado='arquivado' ORDER BY id DESC")]
    return {"itens": itens, "revisar": revisar, "lixeira": lixeira, "pastas": db.pastas(c)}


@app.post("/api/itens/editar", dependencies=[Depends(exige_login)])
def editar_itens(body: Edicao, c=Depends(conexao)):
    """Feito, Excluir, Restaurar, Mover e criticidade de um ou vários itens: mesmo validador das ações da IA,
    tudo ou nada, num grupo só do diário (um Desfazer)."""
    validas = []
    for i in dict.fromkeys(body.ids):
        try:
            validas.append(chat.validar(c, chat.Acao(tipo=body.campo, item_id=i, valor=body.valor), datetime.now())[0])
        except ValueError as e:
            raise HTTPException(404 if "inexistente" in str(e) else 422, f"#{i}: {e}")
    grupo = str(uuid.uuid4())
    n = sum(chat.aplicar(c, a, grupo) for a in validas)
    if not n:
        return {"grupo": None, "descricao": None, "n": 0}
    descricao = (c.execute("SELECT descricao FROM alteracao WHERE grupo=?", (grupo,)).fetchone()[0] if n == 1
                 else chat.frase_lote(body.campo, validas[0].valor, n))
    return {"grupo": grupo, "descricao": descricao, "n": n}


@app.post("/api/itens", dependencies=[Depends(exige_login)])
def criar_item(body: NovoItem, c=Depends(conexao)):
    """Tarefa criada à mão: sem IA. Prazo e prioridade pelas mesmas regras do classificador."""
    agora, titulo, texto_prazo = datetime.now(), body.titulo.strip(), (body.prazo or "").strip()
    db.pastas(c)
    pasta = db.slug_de(body.contexto)
    if not titulo:
        raise HTTPException(422, "título vazio")
    if not pasta:
        raise HTTPException(422, "pasta inexistente")
    prazo_em = rules.resolver_prazo(texto_prazo, agora) if texto_prazo else None
    if texto_prazo and not prazo_em:
        raise HTTPException(422, f"não entendi a data “{texto_prazo}”. Tente “sexta 14h”, “amanhã” ou “dia 20”.")
    cid = str(uuid.uuid4())
    db.nova_captura(c, cid, titulo, "manual")
    c.execute("UPDATE captura SET status='ok' WHERE id=?", (cid,))
    iid = c.execute("INSERT INTO item(captura_id,tipo,titulo,contexto,prazo_texto,prazo_em,prioridade,tags,criado_em) "
                    "VALUES(?,?,?,?,?,?,?,'[]',?)",
                    (cid, body.tipo, titulo, pasta, texto_prazo or None, prazo_em,
                     body.prioridade or rules.prioridade(prazo_em, titulo, agora), db.agora())).lastrowid
    c.commit()
    return {"id": iid, "descricao": f"“{titulo}” criado em {db.nome_pasta(pasta)}"}


class NovaPasta(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    descricao: str = Field(default="", max_length=200)  # o que entra aqui: vai para o prompt da IA


class ApagaPasta(BaseModel):
    destino: str = Field(min_length=1, max_length=40)  # slug de outra pasta, ou "lixeira"


@app.post("/api/pastas", dependencies=[Depends(exige_login)])
def criar_pasta(body: NovaPasta, c=Depends(conexao)):
    try:
        slug = db.criar_pasta(c, body.nome, body.descricao.strip())
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"slug": slug, "nome": db.nome_pasta(slug)}


@app.post("/api/pastas/{slug}/apagar", dependencies=[Depends(exige_login)])
def apagar_pasta(slug: str, body: ApagaPasta, c=Depends(conexao)):
    """Os itens nunca somem junto: vão para outra pasta ou para a Lixeira (com diário), depois a pasta é removida."""
    db.pastas(c)
    if slug == db.FIXA:
        raise HTTPException(422, f"a pasta {db.nome_pasta(db.FIXA)} não pode ser apagada")
    if not any(p["slug"] == slug for p in db.PASTAS):
        raise HTTPException(404, "pasta não existe")
    lixeira = body.destino == "lixeira"
    destino = db.FIXA if lixeira else db.slug_de(body.destino)
    if not destino or destino == slug:
        raise HTTPException(422, "escolha outra pasta para os itens")
    nome, grupo = db.nome_pasta(slug), str(uuid.uuid4())
    itens = c.execute("SELECT id, estado FROM item WHERE contexto=?", (slug,)).fetchall()
    for r in itens:
        if lixeira and r["estado"] != "arquivado":
            chat.aplicar(c, chat.Acao(tipo="estado", item_id=r["id"], valor="arquivado"), grupo)
        chat.aplicar(c, chat.Acao(tipo="contexto", item_id=r["id"], valor=destino), grupo)
    db.remover_pasta(c, slug)
    para = "a Lixeira" if lixeira else db.nome_pasta(destino)
    return {"movidos": len(itens), "grupo": grupo, "descricao": f"Pasta “{nome}” apagada" + (f"; {len(itens)} item(ns) foram para {para}" if itens else "")}


@app.post("/api/layout", dependencies=[Depends(exige_login)])
def salvar_layout(body: Layout, c=Depends(conexao)):
    c.executemany("UPDATE item SET grade_col=?, grade_lin=?, grade_larg=?, grade_alt=? WHERE id=?",
                  [(p.col, p.lin, p.larg, p.alt, p.id) for p in body.itens])
    c.commit()
    return {"ok": True}


@app.post("/api/itens/{item_id}/apagar", dependencies=[Depends(exige_login)])
def apagar_item(item_id: int, c=Depends(conexao)):
    if not db.apagar_de_vez(c, [item_id]):
        raise HTTPException(404, "item não está na Lixeira")
    return {"ok": True}


@app.post("/api/lixeira/esvaziar", dependencies=[Depends(exige_login)])
def esvaziar(c=Depends(conexao)):
    return {"apagados": db.apagar_de_vez(c, [r["id"] for r in c.execute("SELECT id FROM item WHERE estado='arquivado'").fetchall()])}


@app.post("/api/capturas/{captura_id}/reprocessar", dependencies=[Depends(exige_login)])
def reprocessar(captura_id: str, c=Depends(conexao)):
    """Põe uma captura que falhou de volta na fila (o texto original nunca foi alterado)."""
    cur = c.execute("UPDATE captura SET status='pendente', erro=NULL WHERE id=? AND status='falhou'", (captura_id,))
    c.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "captura não encontrada ou não falhou")
    return {"ok": True}


@app.get("/api/alteracoes", dependencies=[Depends(exige_login)])
def alteracoes(c=Depends(conexao)):
    """Últimos grupos de edições automáticas (do editor e do chat), com o que mudou, para Desfazer."""
    grupos = [r["grupo"] for r in c.execute(
        "SELECT grupo FROM alteracao GROUP BY grupo ORDER BY MAX(id) DESC LIMIT 8")]
    saida = []
    for g in grupos:
        linhas = c.execute("SELECT descricao, desfeito FROM alteracao WHERE grupo=? ORDER BY id", (g,)).fetchall()
        saida.append({"grupo": g, "descricoes": [l["descricao"] for l in linhas],
                      "desfeito": all(l["desfeito"] for l in linhas)})
    return saida


class IdGrupo(BaseModel):
    grupo: str = Field(min_length=8, max_length=64)


@app.post("/api/desfazer", dependencies=[Depends(exige_login)])
def desfazer(body: IdGrupo, c=Depends(conexao)):
    return {"revertidas": chat.desfazer(c, body.grupo)}


@app.post("/api/capturas/{captura_id}/como-nota", dependencies=[Depends(exige_login)])
def como_nota(captura_id: str, c=Depends(conexao)):
    """Instrução que o editor não conseguiu aplicar: o usuário manda tratar o texto como anotação comum."""
    cur = c.execute("UPDATE captura SET status='pendente', erro='forcar_nota' WHERE id=? AND status='falhou'", (captura_id,))
    c.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "captura não encontrada ou não falhou")
    return {"ok": True}


class Turno(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=2000)


class MsgChat(BaseModel):
    mensagem: str = Field(min_length=1, max_length=1000)
    historico: list[Turno] = Field(default_factory=list, max_length=6)


@app.post("/api/chat", dependencies=[Depends(exige_login)])
def conversar(body: MsgChat, c=Depends(conexao)):
    try:
        return chat.conversar(c, body.mensagem, [t.model_dump() for t in body.historico])
    except RuntimeError:
        raise HTTPException(503, "modelo indisponível (Ollama ligado?)")


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
