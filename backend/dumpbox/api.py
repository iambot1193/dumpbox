"""API + PWA. Rodar: uvicorn dumpbox.api:app --host 127.0.0.1 --port 8000 (expor só via Tailscale)."""
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, chat, classifier, db, ollama_mgr, setup

# no exe (PyInstaller) os arquivos da web ficam em sys._MEIPASS
WEB = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "web"


def processar_pendentes(c) -> int:
    """Classifica capturas pendentes, uma por vez. Retorna quantas processou."""
    n = 0
    for row in c.execute("SELECT id, texto FROM captura WHERE status='pendente' ORDER BY criado_em").fetchall():
        r = classifier.classificar(row["texto"], datetime.now(), ollama_mgr.modelo())
        db.salvar_resultado(c, row["id"], r)
        n += 1
    return n


def _worker(parar: threading.Event) -> None:
    c = db.conectar()
    while not parar.is_set():
        try:
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


class NovoEstado(BaseModel):
    estado: str = Field(pattern="^(catalogado|feito|arquivado)$")


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
    return {"configurado": bool(os.getenv("DUMPBOX_PASSWORD_HASH")), "preparo": ollama_mgr.ESTADO}


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
    return {"nova": db.nova_captura(c, body.id, body.texto.strip())}


@app.get("/api/itens", dependencies=[Depends(exige_login)])
def listar_itens(c=Depends(conexao)):
    itens = [dict(r) for r in c.execute("SELECT * FROM item WHERE estado!='arquivado' ORDER BY criado_em DESC, id DESC")]
    revisar = [dict(r) for r in c.execute(
        "SELECT id,texto,status,erro FROM captura WHERE status IN ('pendente','falhou') ORDER BY criado_em DESC")]
    return {"itens": itens, "revisar": revisar}


@app.post("/api/itens/{item_id}/estado", dependencies=[Depends(exige_login)])
def mudar_estado(item_id: int, body: NovoEstado, c=Depends(conexao)):
    cur = c.execute("UPDATE item SET estado=? WHERE id=?", (body.estado, item_id))
    c.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "item não existe")
    return {"ok": True}


@app.post("/api/capturas/{captura_id}/reprocessar", dependencies=[Depends(exige_login)])
def reprocessar(captura_id: str, c=Depends(conexao)):
    """Põe uma captura que falhou de volta na fila (o texto original nunca foi alterado)."""
    cur = c.execute("UPDATE captura SET status='pendente', erro=NULL WHERE id=? AND status='falhou'", (captura_id,))
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


class IdProposta(BaseModel):
    id: str = Field(min_length=4, max_length=40)


@app.post("/api/chat", dependencies=[Depends(exige_login)])
def conversar(body: MsgChat, c=Depends(conexao)):
    try:
        return chat.conversar(c, body.mensagem, [t.model_dump() for t in body.historico])
    except RuntimeError:
        raise HTTPException(503, "modelo indisponível (Ollama ligado?)")


@app.post("/api/chat/confirmar", dependencies=[Depends(exige_login)])
def confirmar(body: IdProposta, c=Depends(conexao)):
    try:
        chat.confirmar(c, body.id)
    except KeyError:
        raise HTTPException(404, "proposta expirada ou já usada")
    return {"ok": True}


@app.post("/api/chat/cancelar", dependencies=[Depends(exige_login)])
def cancelar(body: IdProposta):
    chat.cancelar(body.id)
    return {"ok": True}


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
