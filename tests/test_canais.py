"""Bots (Telegram) e lembretes sem rede: mensagens inventadas, Telegram falso via httpx.MockTransport.
Roda com `PYTHONUTF8=1 python tests/test_canais.py` (ou pytest)."""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
TMP = Path(tempfile.mkdtemp())
os.environ["DUMPBOX_DB"] = str(TMP / "t.db")
os.environ["DUMPBOX_HOME"] = str(TMP)

import httpx  # noqa: E402

from dumpbox import chat, db, lembretes  # noqa: E402
from dumpbox.canais import base, telegram  # noqa: E402


def _item(c, titulo, prazo=None, lembrete=None, cap="x"):
    db.nova_captura(c, cap, titulo)
    return c.execute("INSERT INTO item(captura_id,tipo,titulo,contexto,prazo_em,prioridade,estado,criado_em,lembrete) "
                     "VALUES(?,'tarefa',?,'casa',?,'media','catalogado',?,?)", (cap, titulo, prazo, db.agora(), lembrete)).lastrowid


def test_tratar():
    c = db.conectar()
    assert base.tratar(c, "telegram", "1", "10", "comprar pão") == "anotado ✓"
    assert c.execute("SELECT origem FROM captura WHERE id='tg-1-10'").fetchone()["origem"] == "telegram"
    assert base.tratar(c, "telegram", "1", "10", "comprar pão") is None, "reenvio não duplica"
    assert c.execute("SELECT COUNT(*) FROM captura WHERE id='tg-1-10'").fetchone()[0] == 1
    assert "nada com prazo" in base.tratar(c, "telegram", "1", "11", "/hoje").lower()

    i = _item(c, "Ir ao dentista", "2026-11-20", cap="d")
    def falso(c_, pedido, hist):  # IA falsa: aplica de verdade pelo caminho do chat (diário + desfazer)
        g = "g-teste"
        chat._mudar(c_, i, "estado", "feito", g, None); c_.commit()
        return {"resposta": "Feito.", "feitas": ["Ir ao dentista: feito"], "grupo": g}
    r = base.tratar(c, "telegram", "1", "12", "? marca o dentista como feito", conversar=falso)
    assert r.startswith("Feito.") and "✓" in r
    assert c.execute("SELECT estado FROM item WHERE id=?", (i,)).fetchone()[0] == "feito"
    assert base.tratar(c, "telegram", "1", "13", "/desfazer").startswith("Desfeito")
    assert c.execute("SELECT estado FROM item WHERE id=?", (i,)).fetchone()[0] == "catalogado"
    assert base.tratar(c, "telegram", "1", "14", "/desfazer") == "Nada para desfazer."

    def caiu(*a):
        raise RuntimeError("ConnectError")
    assert "não respondeu" in base.tratar(c, "telegram", "1", "15", "? oi", conversar=caiu)
    assert all(not base.excedeu("spam", 0.0) for _ in range(base.LIMITE)) and base.excedeu("spam", 1.0)


def test_lembretes():
    c = db.conectar()
    i = _item(c, "Pagar luz", "2026-12-01T10:00", 30, cap="l")
    enviados = []
    assert lembretes.avisar(c, enviados.append, datetime(2026, 12, 1, 9, 0)) == 0, "cedo demais"
    assert lembretes.avisar(c, enviados.append, datetime(2026, 12, 1, 9, 31)) == 1 and "Pagar luz" in enviados[0]
    assert lembretes.avisar(c, enviados.append, datetime(2026, 12, 1, 9, 40)) == 0, "avisa uma vez só"
    chat._mudar(c, i, "prazo", "2026-12-02T10:00", "g2", None); c.commit()
    assert lembretes.avisar(c, enviados.append, datetime(2026, 12, 2, 9, 31)) == 1, "prazo mudou: reavisa"

    def falha(t):
        raise httpx.ConnectError("sem rede")
    j = _item(c, "Só dia", "2026-12-05", 0, cap="s")  # só dia = 9h
    assert lembretes.avisar(c, falha, datetime(2026, 12, 5, 9, 1)) == 0
    assert c.execute("SELECT avisado_em FROM item WHERE id=?", (j,)).fetchone()[0] is None, "falhou: continua pendente"
    out = []
    assert lembretes.avisar(c, out.append, datetime(2026, 12, 6, 8, 0)) == 1 and out[0].startswith("🔔 atrasado")


def test_telegram_polling():
    c = db.conectar()
    chamadas = []
    def responde(req: httpx.Request):
        metodo, corpo = req.url.path.rsplit("/", 1)[1], json.loads(req.content or b"{}")
        chamadas.append((metodo, corpo))
        if metodo == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": [
                {"update_id": 7, "message": {"message_id": 1, "chat": {"id": 42}, "text": "lavar carro sábado"}},
                {"update_id": 8, "message": {"message_id": 2, "chat": {"id": 666}, "text": "sou estranho"}}]})
        return httpx.Response(200, json={"ok": True, "result": {}})
    bot = telegram.Bot("TOKEN-FALSO", {"42"}, httpx.Client(transport=httpx.MockTransport(responde)))
    assert bot.uma_vez(c, 0, espera=0) == 9
    enviados = [b for m, b in chamadas if m == "sendMessage"]
    assert enviados == [{"chat_id": "42", "text": "anotado ✓"}], enviados
    assert not c.execute("SELECT 1 FROM captura WHERE texto='sou estranho'").fetchone(), "estranho ignorado"
    cap = "tg-42-1"
    c.execute("UPDATE captura SET status='ok' WHERE id=?", (cap,))
    c.execute("INSERT INTO item(captura_id,tipo,titulo,contexto,prioridade,estado,criado_em) VALUES(?,'tarefa','Lavar carro','casa','media','catalogado',?)", (cap, db.agora()))
    c.commit()
    chamadas.clear()
    bot.uma_vez(c, 9, espera=0)
    assert any("Lavar carro" in b.get("text", "") for m, b in chamadas if m == "sendMessage"), "avisa o que a IA criou"
    assert not bot.esperando


def _zap(remote, texto, msg_id, from_me=False):
    return {"event": "messages.upsert", "instance": "dumpbox",
            "data": {"key": {"remoteJid": remote, "fromMe": from_me, "id": msg_id}, "message": {"conversation": texto}}}


def test_whatsapp():
    import hashlib
    import hmac as h
    os.environ["DUMPBOX_WORKER"] = "0"
    os.environ["DUMPBOX_ZAP_PERMITIDOS"] = "+55 11 90000-0001"
    from fastapi.testclient import TestClient
    from dumpbox import api
    from dumpbox.canais import whatsapp
    enviados = []
    falso = httpx.Client(transport=httpx.MockTransport(lambda r: enviados.append(json.loads(r.content)) or httpx.Response(200, json={})))
    evo = whatsapp.Evolution("http://evo", "dumpbox", "k", "segredo-zap", falso)
    whatsapp.provedor = lambda: evo
    t = TestClient(api.app)
    eu = "5511900000001@s.whatsapp.net"
    assert t.post("/api/canais/whatsapp", json=_zap(eu, "oi", "A1")).status_code == 401, "sem segredo"
    hd = {"x-dumpbox-segredo": "segredo-zap"}
    assert t.post("/api/canais/whatsapp", json=_zap(eu, "trocar óleo do carro", "A1"), headers=hd).status_code == 200
    assert enviados[-1] == {"number": "5511900000001", "text": "anotado ✓"}
    c = db.conectar()
    assert c.execute("SELECT origem FROM captura WHERE id='zap-5511900000001-A1'").fetchone()["origem"] == "whatsapp"
    n = len(enviados)
    t.post("/api/canais/whatsapp", json=_zap(eu, "trocar óleo do carro", "A1"), headers=hd)  # reenvio
    t.post("/api/canais/whatsapp", json=_zap(eu, "resposta do bot", "A2", from_me=True), headers=hd)  # loop
    t.post("/api/canais/whatsapp", json=_zap("5511988887777@s.whatsapp.net", "estranho", "A3"), headers=hd)
    t.post("/api/canais/whatsapp", json=_zap("123-456@g.us", "grupo", "A4"), headers=hd)
    assert len(enviados) == n and c.execute("SELECT COUNT(*) FROM captura WHERE origem='whatsapp'").fetchone()[0] == 1

    cloud = whatsapp.CloudAPI("tk", "999", "app-secret", "verifica-123", falso)
    whatsapp.provedor = lambda: cloud
    assert t.get("/api/canais/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verifica-123", "hub.challenge": "42"}).text == "42"
    assert t.get("/api/canais/whatsapp", params={"hub.verify_token": "errado", "hub.challenge": "42"}).status_code == 403
    corpo = json.dumps({"entry": [{"changes": [{"value": {"messages": [
        {"from": "5511900000001", "id": "wamid.X", "type": "text", "text": {"body": "comprar ração"}}]}}]}]}).encode()
    ass = "sha256=" + h.new(b"app-secret", corpo, hashlib.sha256).hexdigest()
    assert t.post("/api/canais/whatsapp", content=corpo, headers={"x-hub-signature-256": "sha256=00"}).status_code == 401, "assinatura inválida"
    assert t.post("/api/canais/whatsapp", content=corpo, headers={"x-hub-signature-256": ass}).status_code == 200
    assert enviados[-1]["to"] == "5511900000001" and enviados[-1]["text"]["body"] == "anotado ✓"


def test_busca_sem_modelo():
    """Sem o modelo de embedding (Ollama fora), a busca do chat cai para palavras e o contexto ainda traz nota antiga."""
    from dumpbox import busca
    def fora(*a, **k):
        raise httpx.ConnectError("sem ollama")
    busca.embed = fora
    c = db.conectar()
    alvo = _item(c, "Renovar seguro do carro", cap="seg")
    c.execute("UPDATE item SET detalhe='cotar 3 corretoras' WHERE id=?", (alvo,)); c.commit()
    for k in range(70):  # empurra o alvo para fora dos últimos 60
        _item(c, f"Item de enchimento {k}", cap=f"e{k}")
    assert busca.buscar(c, "o que anotei sobre corretoras?")[:1] == [alvo]
    assert f"#{alvo} |" in chat.contexto_itens(c, detalhado=True, extras=[alvo])
    assert f"#{alvo} |" not in chat.contexto_itens(c, detalhado=True)


if __name__ == "__main__":
    for t in (test_tratar, test_lembretes, test_telegram_polling, test_whatsapp, test_busca_sem_modelo):
        t()
        print("ok", t.__name__)
