"""Bot do Telegram por long polling (getUpdates): o PC pergunta ao Telegram, nada fica exposto na internet.
Liga sozinho se DUMPBOX_TG_TOKEN e DUMPBOX_TG_PERMITIDOS (chat_ids, vírgula) estiverem no config.env."""
import os
import threading

import httpx

from .. import config, db
from . import base

OFFSET = config.HOME / "telegram.offset"  # reiniciar não repete mensagens


class Bot:
    def __init__(self, token: str, permitidos: set[str], cliente: httpx.Client | None = None):
        self.url = f"https://api.telegram.org/bot{token}/"
        self.permitidos = permitidos
        self.http = cliente or httpx.Client(timeout=40)
        self.esperando: dict[str, str] = {}  # captura_id -> chat_id: avisa o que a IA criou

    def chamar(self, metodo: str, **dados):
        r = self.http.post(self.url + metodo, json=dados)
        r.raise_for_status()  # a mensagem de erro do httpx traz a URL com o token: nunca logar `e`
        return r.json()["result"]

    def enviar(self, chat_id: str, texto: str) -> None:
        self.chamar("sendMessage", chat_id=chat_id, text=texto[:4000])

    def avisar_todos(self, texto: str) -> None:
        for p in self.permitidos:
            self.enviar(p, texto)

    def uma_vez(self, c, offset: int, espera: int = 30) -> int:
        """Busca e trata um lote de mensagens. Devolve o próximo offset."""
        for u in self.chamar("getUpdates", offset=offset, timeout=espera, allowed_updates=["message"]):
            offset = u["update_id"] + 1
            m = u.get("message") or {}
            chat_id = str(m.get("chat", {}).get("id", ""))
            if chat_id not in self.permitidos or "text" not in m:
                continue  # outra pessoa: ignora sem responder e sem guardar o texto
            resp = base.tratar(c, "telegram", chat_id, str(m["message_id"]), m["text"])
            if resp == "anotado ✓":
                self.esperando[base.id_captura("telegram", chat_id, str(m["message_id"]))] = chat_id
            if resp:
                self.enviar(chat_id, resp)
        for cap, chat_id in list(self.esperando.items()):
            if (txt := base.criados(c, cap)) is not None:
                self.enviar(chat_id, txt)
                del self.esperando[cap]
        return offset


def _ler_offset() -> int:
    try:
        return int(OFFSET.read_text())
    except (OSError, ValueError):
        return 0


def rodar(parar: threading.Event, bot: Bot) -> None:
    c = db.conectar()
    offset = _ler_offset()
    while not parar.is_set():
        try:
            novo = bot.uma_vez(c, offset, espera=20 if bot.esperando else 30)
            if novo != offset:
                offset = novo
                OFFSET.write_text(str(offset))
        except Exception:  # rede caiu, token errado: tenta de novo sem derrubar o servidor
            parar.wait(15)


def descobrir(token: str) -> set[str]:
    """Quem mandou mensagem ao bot (para preencher DUMPBOX_TG_PERMITIDOS). Não consome as mensagens."""
    return {str(u["message"]["chat"]["id"]) for u in Bot(token, set()).chamar("getUpdates", timeout=0) if "message" in u}


def iniciar(parar: threading.Event) -> bool:
    token = os.getenv("DUMPBOX_TG_TOKEN", "")
    permitidos = {p.strip() for p in os.getenv("DUMPBOX_TG_PERMITIDOS", "").split(",") if p.strip()}
    if not token or not permitidos:
        return False
    global ATIVO
    ATIVO = Bot(token, permitidos)
    threading.Thread(target=rodar, args=(parar, ATIVO), daemon=True).start()
    return True


ATIVO: Bot | None = None  # lembretes usam (api._avisos)


if __name__ == "__main__":  # python -m dumpbox.canais.telegram: grava token e seu chat_id no config.env
    tk = os.getenv("DUMPBOX_TG_TOKEN") or input("Token do @BotFather: ").strip()
    input("No Telegram, mande /start para o seu bot e aperte Enter aqui...")
    ids = descobrir(tk)
    if not ids:
        raise SystemExit("Nenhuma mensagem chegou ao bot. Mande /start e rode de novo.")
    linhas = [l for l in (config.ARQ.read_text(encoding="utf-8").splitlines() if config.ARQ.exists() else [])
              if not l.startswith(("DUMPBOX_TG_TOKEN=", "DUMPBOX_TG_PERMITIDOS="))]
    config.ARQ.parent.mkdir(parents=True, exist_ok=True)
    config.ARQ.write_text("\n".join(linhas + [f"DUMPBOX_TG_TOKEN={tk}", f"DUMPBOX_TG_PERMITIDOS={','.join(sorted(ids))}"]) + "\n", encoding="utf-8")
    print(f"Pronto: {len(ids)} chat(s) permitido(s) em {config.ARQ}. Reinicie o dumpbox.")
