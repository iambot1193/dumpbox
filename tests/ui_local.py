"""Modo celular (web/local.js): o app sem servidor, como fica no GitHub Pages. Chrome headless, tela de celular.
Serve a raiz do repo e abre /web/?local=1 (subcaminho, igual ao Pages). Datas conferidas contra rules.py.
No fim conecta a um servidor de verdade (banco temporário, outra origem = CORS + token) e confere o envio das notas.

    python tests/ui_local.py        (precisa de playwright; caminho extra: DUMPBOX_PW_PATH)
"""
import functools
import http.server
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [p for p in (os.getenv("DUMPBOX_PW_PATH"), str(RAIZ / "backend")) if p]
os.environ.update(DUMPBOX_HOME=tempfile.mkdtemp(prefix="dumpbox_local_"), DUMPBOX_WORKER="0", DUMPBOX_SECRET="teste-local", DUMPBOX_NO_BROWSER="1")
from dumpbox import auth, db  # noqa: E402
from dumpbox.rules import resolver_prazo  # noqa: E402
os.environ["DUMPBOX_PASSWORD_HASH"] = auth.hash_senha("senha-de-teste")
from playwright.sync_api import sync_playwright  # noqa: E402

class Mudo(http.server.SimpleHTTPRequestHandler):
    log_message = lambda *a: None


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Mudo, directory=str(RAIZ)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_port}/web/?local=1"
PC = "http://127.0.0.1:8125"
pc = subprocess.Popen([sys.executable, "-m", "uvicorn", "dumpbox.api:app", "--port", "8125", "--log-level", "warning"], cwd=RAIZ,
                      env={**os.environ, "PYTHONPATH": str(RAIZ / "backend"), "DUMPBOX_ORIGENS": f"http://127.0.0.1:{srv.server_port}"})
falhas = []


def ok(cond, nome):
    print(("ok   " if cond else "FALHA"), nome, flush=True)
    if not cond:
        falhas.append(nome)


api = """async ([url, corpo]) => { const r = await fetch(url, corpo === null ? {} : { method: 'POST', body: JSON.stringify(corpo) });
  return [r.status, await r.json()]; }"""
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    g = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
    erros = []
    g.on("pageerror", lambda e: erros.append(str(e)))
    g.on("response", lambda r: erros.append(f"{r.status} {r.url}") if r.status >= 400 and r.status != 401 else None)
    g.goto(URL)
    g.wait_for_selector("#nav .fold")
    ok("Modo celular" in g.inner_text("#prep"), "aviso de modo celular no topo")
    ok(g.locator("#fab").is_hidden() and g.locator("#foto").is_hidden(), "sem chat e sem foto (precisam da IA)")

    g.fill("#txt", "comprar pilhas\nAA e AAA")
    g.click("#guardar")
    g.click('[data-alvo="outro"]')
    g.wait_for_selector('#vista article h3:text-is("comprar pilhas")')
    ok(g.evaluate("JSON.parse(localStorage['dumpbox.fila'] || '[]').length") == 0, "nota sai da fila e vira item local")

    st, r = g.evaluate(api, ["/api/itens", {"titulo": "Pagar boleto", "contexto": "Finanças", "tipo": "tarefa", "prazo": "amanhã 10h"}])
    ok(st == 200 and "Finanças" in r["descricao"], "cria tarefa à mão")
    it = next(i for i in g.evaluate(api, ["/api/itens", None])[1]["itens"] if i["titulo"] == "Pagar boleto")
    ok(it["prazo_em"] == resolver_prazo("amanhã 10h", datetime.now()) and it["prioridade"] == "alta", f"prazo e prioridade por regra {it['prazo_em']}")
    for t in ["hoje", "depois de amanhã", "sexta 14h", "segunda", "dia 5", "dia 28 9:30", "em 2 semanas", "daqui a três dias", "semana que vem"]:
        st, r = g.evaluate(api, [f"/api/itens/{it['id']}/editar", {"mudancas": {"prazo": t}}])
        got = next(i for i in g.evaluate(api, ["/api/itens", None])[1]["itens"] if i["id"] == it["id"])["prazo_em"]
        ok(got == resolver_prazo(t, datetime.now()), f"prazo “{t}” igual ao rules.py ({got})")
    ok(g.evaluate(api, ["/api/itens", {"titulo": "x", "contexto": "casa", "tipo": "tarefa", "prazo": "qualquer dia"}])[0] == 422, "data não entendida dá 422")

    st, r = g.evaluate(api, ["/api/itens/editar", {"ids": [it["id"]], "campo": "estado", "valor": "feito"}])
    ok(r["n"] == 1 and "feito" in r["descricao"], "marca feito")
    g.evaluate(api, ["/api/desfazer", {"grupo": r["grupo"]}])
    g.reload()
    g.wait_for_selector("#nav .fold")
    it = next(i for i in g.evaluate(api, ["/api/itens", None])[1]["itens"] if i["id"] == it["id"])
    ok(it["estado"] == "catalogado", "Desfazer volta e tudo continua depois de recarregar")
    ok(g.evaluate(api, ["/api/pastas", {"nome": "Projetos pessoais"}])[1]["slug"] == "projetos_pessoais", "cria pasta")

    ok(g.evaluate("navigator.serviceWorker.ready.then(r => r.scope)").endswith("/web/"), "service worker no subcaminho (funciona offline)")
    g.context.set_offline(True)
    g.reload()
    g.wait_for_selector("#nav .fold")
    ok(g.locator('[data-alvo="projetos_pessoais"]').count() == 1, "abre sem internet com os dados do aparelho")

    # ---- cópia do PC por arquivo (python -m dumpbox.exportar): entra no banco do aparelho, o que nasceu aqui fica ----
    cpd = db.conectar()
    cpd.execute("INSERT INTO captura(id,texto,criado_em,status) VALUES('seed','x','2026-01-01','ok')")
    cpd.execute("INSERT INTO pasta(slug,nome,descricao,ordem,criado_em) VALUES('mercado','Mercado','',99,'2026-01-01')")
    for t, ctx in [("Item do PC 1", "mercado"), ("Item do PC 2", "casa")]:
        cpd.execute("INSERT INTO item(captura_id,tipo,titulo,contexto,prioridade,estado,criado_em) VALUES('seed','tarefa',?,?,'baixa','catalogado','2026-01-01')", (t, ctx))
    cpd.commit()
    arquivo = Path(tempfile.mkdtemp()) / "copia.json"
    subprocess.run([sys.executable, "-m", "dumpbox.exportar", str(arquivo)], cwd=RAIZ, env={**os.environ, "PYTHONPATH": str(RAIZ / "backend")}, check=True, capture_output=True)
    for t in ["Item do PC 1", "Item do PC 2"]:
        cpd.execute("DELETE FROM item WHERE titulo=?", (t,))  # no PC somem: se o celular reenviar a cópia, o teste vê
    cpd.commit()
    g.click("#prep")
    with g.expect_file_chooser() as fc:
        g.click(".dlg button:has-text('Importar cópia')")
    fc.value.set_files(str(arquivo))
    g.wait_for_selector("#toast >> text=2 itens copiados do PC")
    titulos = [i["titulo"] for i in g.evaluate(api, ["/api/itens", None])[1]["itens"]]
    ok({"Item do PC 1", "Item do PC 2", "comprar pilhas", "Pagar boleto"} <= set(titulos), f"cópia entra e o que nasceu no celular fica {titulos}")
    ok(g.locator('[data-alvo="mercado"]').count() == 1, "pasta do PC aparece no celular")

    # ---- conectar ao PC: endereço pelo aviso do topo, senha do PC, notas locais sobem ----
    g.context.set_offline(False)
    g.reload()
    g.wait_for_selector("#nav .fold")
    g.once("dialog", lambda d: d.accept(PC))
    g.click("#prep")
    g.click(".dlg button:has-text('Conectar')")
    g.wait_for_selector("#login:not([hidden])")
    ok(g.locator("#login button", has_text="desconectar").count() == 1, "login do PC com opção de desconectar")
    g.fill("#senha", "senha-de-teste")
    g.click("#entrar")
    g.wait_for_selector("#toast >> text=enviado", timeout=10000)
    c = db.conectar()
    cap = c.execute("SELECT texto FROM captura WHERE texto LIKE 'comprar pilhas%'").fetchone()
    tarefa = c.execute("SELECT contexto, prazo_em FROM item WHERE titulo='Pagar boleto'").fetchone()
    ok(cap and cap[0] == "comprar pilhas\nAA e AAA","nota intacta vai para a IA do PC (texto completo)")
    ok(tarefa and tuple(tarefa) == ("financas", resolver_prazo("semana que vem", datetime.now())), "tarefa editada vai com pasta e prazo")
    ok(not c.execute("SELECT 1 FROM item WHERE titulo LIKE 'Item do PC%'").fetchone(), "cópia do PC não volta para o PC")
    ok([i["titulo"] for i in g.evaluate("JSON.parse(localStorage['dumpbox.local']).itens")] == ["Item do PC 1", "Item do PC 2"], "só a cópia fica no aparelho")
    ok(g.evaluate("!!localStorage['dumpbox.token']") and g.locator("#fab").is_visible(), "conectado: token salvo, chat da IA aparece")
    g.reload()
    g.wait_for_selector("#nav .fold")
    ok(g.locator("#app").is_visible(), "continua logado no PC depois de recarregar (token)")
    ok(not erros, f"sem erros no console/rede {erros[:3]}")
    b.close()
srv.shutdown()
pc.terminate()
print("FALHAS:", falhas if falhas else "nenhuma")
sys.exit(1 if falhas else 0)
