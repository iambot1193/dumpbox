"""Modo celular (web/local.js): o app sem servidor, como fica no GitHub Pages. Chrome headless, tela de celular.
Serve a raiz do repo e abre /web/?local=1 (subcaminho, igual ao Pages). Datas conferidas contra rules.py.

    python tests/ui_local.py        (precisa de playwright; caminho extra: DUMPBOX_PW_PATH)
"""
import functools
import http.server
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [p for p in (os.getenv("DUMPBOX_PW_PATH"), str(RAIZ / "backend")) if p]
from dumpbox.rules import resolver_prazo  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

class Mudo(http.server.SimpleHTTPRequestHandler):
    log_message = lambda *a: None


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Mudo, directory=str(RAIZ)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_port}/web/?local=1"
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
    g.on("response", lambda r: erros.append(f"{r.status} {r.url}") if r.status >= 400 else None)
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
    ok(not erros, f"sem erros no console/rede {erros[:3]}")
    b.close()
srv.shutdown()
print("FALHAS:", falhas if falhas else "nenhuma")
sys.exit(1 if falhas else 0)
