"""API sem Ollama: classificar é trocado por um falso. Roda com `python tests/test_api.py` (ou pytest)."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ["DUMPBOX_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["DUMPBOX_WORKER"] = "0"
os.environ["DUMPBOX_SECRET"] = "segredo-de-teste"

from dumpbox import api, auth, classifier, db  # noqa: E402
from dumpbox.schema import Item  # noqa: E402

os.environ["DUMPBOX_PASSWORD_HASH"] = auth.hash_senha("senha-certa")
from fastapi.testclient import TestClient  # noqa: E402


def _fake(texto, agora, modelo="fake"):
    if "falha" in texto:
        return classifier.Resultado(None, modelo, "t", 1, "ValidationError")
    it = Item(tipo="tarefa", titulo="Pagar luz", contexto="financas", prazo_texto="amanhã", prazo_em="2026-11-11", prioridade="alta")
    return classifier.Resultado([it], modelo, "t", 5)


def test_fluxo():
    classifier.classificar = _fake  # api.processar_pendentes usa classifier.classificar
    c = TestClient(api.app)
    # sem login: tudo da API é negado
    assert c.get("/api/itens").status_code == 401
    assert c.post("/api/capturas", json={"id": "12345678", "texto": "x"}).status_code == 401
    # senha errada, depois certa
    assert c.post("/api/login", json={"senha": "errada"}).status_code == 401
    assert c.post("/api/login", json={"senha": "senha-certa"}).status_code == 200
    # captura idempotente (mesmo UUID do cliente não duplica)
    assert c.post("/api/capturas", json={"id": "aaaaaaaa-1", "texto": "pagar luz amanhã"}).json()["nova"] is True
    assert c.post("/api/capturas", json={"id": "aaaaaaaa-1", "texto": "pagar luz amanhã"}).json()["nova"] is False
    c.post("/api/capturas", json={"id": "bbbbbbbb-2", "texto": "isto vai falha"})
    # pendentes aparecem em 'revisar'; worker processa
    assert len(c.get("/api/itens").json()["revisar"]) == 2
    conn = db.conectar()
    assert api.processar_pendentes(conn) == 2
    r = c.get("/api/itens").json()
    assert len(r["itens"]) == 1 and r["itens"][0]["titulo"] == "Pagar luz"
    assert [x["status"] for x in r["revisar"]] == ["falhou"]  # nota que falhou nunca se perde
    # marcar como feito e validar estado inválido
    iid = r["itens"][0]["id"]
    assert c.post(f"/api/itens/{iid}/estado", json={"estado": "feito"}).status_code == 200
    assert c.post(f"/api/itens/{iid}/estado", json={"estado": "xxx"}).status_code == 422
    assert c.post("/api/itens/999/estado", json={"estado": "feito"}).status_code == 404


def test_rate_limit_e_token():
    assert not auth.token_valido("1.abc") and not auth.token_valido(None)
    assert auth.token_valido(auth.novo_token())
    for _ in range(5):
        assert auth.limite_ok("9.9.9.9")
    assert not auth.limite_ok("9.9.9.9")


if __name__ == "__main__":
    test_fluxo()
    test_rate_limit_e_token()
    print("ok")
