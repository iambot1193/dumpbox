"""Modo celular (web/local.js): o app sem servidor, como fica no GitHub Pages. Chrome headless, tela de celular.
Serve a raiz do repo e abre /web/?local=1 (subcaminho, igual ao Pages). Datas conferidas contra rules.py.
No fim conecta a um servidor de verdade (banco temporário, outra origem = CORS + token) e confere o envio das notas.

    python tests/ui_local.py        (precisa de playwright; caminho extra: DUMPBOX_PW_PATH)
"""
import functools
import json
import http.server
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [p for p in (os.getenv("DUMPBOX_PW_PATH"), str(RAIZ / "backend")) if p]
os.environ.update(DUMPBOX_HOME=tempfile.mkdtemp(prefix="dumpbox_local_"), DUMPBOX_WORKER="0", DUMPBOX_SECRET="teste-local", DUMPBOX_NO_BROWSER="1")
from dumpbox import auth, db  # noqa: E402
from dumpbox.chat import proxima  # noqa: E402
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
import atexit; atexit.register(pc.terminate)  # teste que quebra no meio não deixa o servidor da 8125 vivo


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
    # tutorial do 1º acesso: passa pelos passos, fecha e não volta; "ajuda" reabre
    g.wait_for_selector(".tour")
    ok(g.inner_text(".tour .passo") == "1 de 6", "tutorial abre no 1º acesso")
    time.sleep(.4)  # o destaque desliza até o alvo
    caixa = g.evaluate("(() => { const a = document.querySelector('.furo').getBoundingClientRect(), b = document.getElementById('txt').getBoundingClientRect(); return a.left <= b.left && a.right >= b.right && a.top <= b.top; })()")
    ok(caixa, "passo 1 destaca a caixa de nota")
    for _ in range(3):
        g.locator(".tour button", has_text="Pular passo").click()
    for _ in range(2):
        g.locator(".tour button", has_text="Próximo").click()
    ok("Avisos" in g.inner_text(".tour h4"), "último passo fala dos avisos")
    g.locator(".tour button", has_text="Fechar").click()
    g.reload(); g.wait_for_selector("#nav .fold"); time.sleep(.5)
    ok(g.locator(".tour").count() == 0, "tutorial não volta depois de visto")
    g.locator("#nav button", has_text="mais").click(); g.locator(".menu button", has_text="Ajuda").click()
    ok(g.locator(".tour").count() == 1, "“ajuda” reabre o tutorial")
    # interativo: fazer na tela avança o passo (e a tela continua usável com o tutorial aberto)
    g.locator(".tour button", has_text="Pular passo").click()
    g.click(".brapida"); g.fill(".rapida input", "Tarefa do tutorial"); g.press(".rapida input", "Enter")
    g.wait_for_selector(".tour .passo >> text=3 de 6")
    ok(True, "criar pelo + avança o tutorial")
    g.locator("#vista article", has=g.locator('h3:text-is("Tarefa do tutorial")')).locator(".ok").click()
    g.wait_for_selector(".tour .passo >> text=4 de 6")
    ok(True, "concluir pelo ✓ avança o tutorial")
    g.locator(".tour button", has_text="Sair").click()
    ok(g.locator(".tour, .furo").count() == 0, "Sair fecha o tutorial")
    g.click(".rapida .fx")

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
    # calendário (ISO), data que não existe, "limpar"; texto do card
    edita = lambda m: g.evaluate(api, [f"/api/itens/{it['id']}/editar", {"mudancas": m}])[0]
    prazo_de = lambda: next(i for i in g.evaluate(api, ["/api/itens", None])[1]["itens"] if i["id"] == it["id"])
    ok(edita({"prazo": "2026-12-10T14:30", "detalhe": " código de barras \n"}) == 200 and prazo_de()["prazo_em"] == "2026-12-10T14:30"
       and prazo_de()["detalhe"] == "código de barras", "prazo do calendário e texto do card")
    ok(edita({"prazo": "2026-02-31"}) == 422 and edita({"prazo": "limpar"}) == 200 and prazo_de()["prazo_em"] is None, "data inexistente dá 422; limpar tira o prazo")
    edita({"prazo": "semana que vem"})

    st, r = g.evaluate(api, ["/api/itens/editar", {"ids": [it["id"]], "campo": "estado", "valor": "feito"}])
    ok(r["n"] == 1 and "feito" in r["descricao"], "marca feito")
    g.evaluate(api, ["/api/desfazer", {"grupo": r["grupo"]}])
    g.reload()
    g.wait_for_selector("#nav .fold")
    it = next(i for i in g.evaluate(api, ["/api/itens", None])[1]["itens"] if i["id"] == it["id"])
    ok(it["estado"] == "catalogado", "Desfazer volta e tudo continua depois de recarregar")
    ok(g.evaluate(api, ["/api/pastas", {"nome": "Projetos pessoais"}])[1]["slug"] == "projetos_pessoais", "cria pasta")

    # repetição no aparelho: concluir cria a próxima, igual ao chat.proxima; Desfazer volta
    for prazo_txt, rep in [("dia 30", "mensal"), ("sexta 14h", "semanal"), ("amanhã", "diario")]:
        st, r = g.evaluate(api, ["/api/itens", {"titulo": f"Rep {rep}", "contexto": "casa", "tipo": "tarefa", "prazo": prazo_txt, "repete": rep}])
        base = next(i for i in g.evaluate(api, ["/api/itens", None])[1]["itens"] if i["id"] == r["id"])
        st, e = g.evaluate(api, ["/api/itens/editar", {"ids": [r["id"]], "campo": "estado", "valor": "feito"}])
        its = g.evaluate(api, ["/api/itens", None])[1]["itens"]
        nova = [i for i in its if i["titulo"] == f"Rep {rep}" and i["estado"] == "catalogado"]
        ok(len(nova) == 1 and nova[0]["prazo_em"] == proxima(base["prazo_em"], rep, datetime.now()) and nova[0]["repete"] == rep,
           f"repete {rep}: próxima {nova[0]['prazo_em'] if nova else None} igual ao chat.proxima")
        g.evaluate(api, ["/api/desfazer", {"grupo": e["grupo"]}])
        its = g.evaluate(api, ["/api/itens", None])[1]
        ok(next(i for i in its["itens"] if i["id"] == r["id"])["repete"] == rep and any(i["titulo"] == f"Rep {rep}" for i in its["lixeira"]),
           f"repete {rep}: Desfazer reabre e manda a próxima para a Lixeira")

    # busca em todas as pastas, sem acento
    g.fill("#busca", "PILHAS")
    g.wait_for_selector("h2:text-is('Busca')")
    ok(g.locator("#vista article.c h3").all_inner_texts() == ["comprar pilhas"], "busca acha em qualquer pasta, sem diferenciar maiúscula")
    g.fill("#busca", "")
    g.wait_for_selector("h2:not(:text-is('Busca'))")

    # compartilhar para o dumpbox: o texto chega na caixa de nota
    g.goto(URL + "&title=Video&text=olha%20isso&url=https%3A%2F%2Fexemplo.com")
    g.wait_for_selector("#nav .fold")
    ok(g.input_value("#txt") == "Video\nolha isso\nhttps://exemplo.com" and "text=" not in g.url and "local=1" in g.url, "compartilhado entra na caixa e sai da URL")
    g.fill("#txt", "")

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

    # ---- backup: alerta sem backup, salvar arquivo, restaurar depois de perder os dados ----
    g.wait_for_function("document.querySelector('#prep').textContent.includes('ainda não fez backup')", timeout=5000)
    ok(True, "alerta no topo: ainda sem backup")
    g.click("#prep")
    with g.expect_download() as dl:
        g.click(".dlg button:has-text('Salvar backup')")
    bk = Path(tempfile.mkdtemp()) / dl.value.suggested_filename
    dl.value.save_as(bk)
    dados = json.loads(bk.read_text(encoding="utf-8"))
    ok(dados.get("backup") and len(dados["itens"]) == len(g.evaluate("JSON.parse(localStorage['dumpbox.local']).itens")), "backup tem todos os itens")
    g.wait_for_function("!document.querySelector('#prep').textContent.includes('backup.')", timeout=5000)
    antes = sorted(i["titulo"] for i in g.evaluate(api, ["/api/itens", None])[1]["itens"])
    g.evaluate("localStorage.removeItem('dumpbox.local'); localStorage.removeItem('dumpbox.local.backup_em')")
    g.reload()
    g.wait_for_selector("#nav .fold")
    ok(not g.evaluate(api, ["/api/itens", None])[1]["itens"], "dados apagados (simula limpar o navegador)")
    g.click("#prep")
    with g.expect_file_chooser() as fc:
        g.click(".dlg button:has-text('Restaurar backup')")
    fc.value.set_files(str(bk))
    g.wait_for_selector("#toast >> text=Backup restaurado")
    ok(sorted(i["titulo"] for i in g.evaluate(api, ["/api/itens", None])[1]["itens"]) == antes, "restaurar backup devolve tudo")
    ok(g.locator('[data-alvo="mercado"]').count() == 1, "pastas voltam com o backup")

    # ---- lembretes: por tarefa (X min antes do prazo) e diário; sem permissão de notificação viram aviso na tela ----
    g.context.set_offline(False)
    daqui = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M")
    st, r = g.evaluate(api, ["/api/itens", {"titulo": "Ligar pro dentista", "contexto": "casa", "tipo": "tarefa", "prazo": daqui, "lembrete": 15}])
    ok(st == 200, f"cria tarefa com lembrete {st} {r}")
    g.wait_for_selector("#toast >> text=Lembrete: Ligar pro dentista", timeout=12000)
    ok(True, "lembrete 15 min antes dispara (prazo daqui a 10 min)")
    g.evaluate("localStorage.setItem('dumpbox.avisos', JSON.stringify({diario: '00:00'}))")
    g.reload(); g.wait_for_selector("#nav .fold")
    g.wait_for_selector("#toast >> text=Hoje:", timeout=12000)
    ok("Lembrete: Ligar" not in g.locator("#toast").inner_text(), "lembrete diário aparece 1x e o da tarefa não repete")
    g.evaluate("localStorage.removeItem('dumpbox.avisos')")

    # ---- QR do PC (?pc=): só aceita endereço do Tailscale ----
    g.context.set_offline(False)
    base = g.url.split("?")[0]
    g.goto(base + "?local=1&pc=https://evil.example.com")
    g.wait_for_selector("#nav .fold")
    ok(g.evaluate("localStorage['dumpbox.pc']") is None, "QR com endereço fora do Tailscale é ignorado")
    g.goto(base + "?local=1&pc=" + "https%3A%2F%2Fmeu-pc.tail12ab.ts.net")
    ok(g.evaluate("localStorage['dumpbox.pc']") == "https://meu-pc.tail12ab.ts.net" and "pc=" not in g.url, "QR do Tailscale conecta e limpa o link")
    g.evaluate("localStorage.removeItem('dumpbox.pc')")

    # ---- conectar ao PC: endereço pelo aviso do topo, senha do PC, notas locais sobem ----
    g.goto(base + "?local=1")
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
    tarefa = c.execute("SELECT contexto, prazo_em, detalhe FROM item WHERE titulo='Pagar boleto'").fetchone()
    ok(cap and cap[0] == "comprar pilhas\nAA e AAA","nota intacta vai para a IA do PC (texto completo)")
    ok(tarefa and tuple(tarefa) == ("financas", resolver_prazo("semana que vem", datetime.now()), "código de barras"), "tarefa editada vai com pasta, prazo e texto")
    ok(not c.execute("SELECT 1 FROM item WHERE titulo LIKE 'Item do PC%'").fetchone(), "cópia do PC não volta para o PC")
    ok([i["titulo"] for i in g.evaluate("JSON.parse(localStorage['dumpbox.local']).itens") if i["estado"] == "catalogado"] == ["Item do PC 1", "Item do PC 2"],
       "dos abertos, só a cópia fica no aparelho (feitos e Lixeira não sobem)")
    ok(g.evaluate("!!localStorage['dumpbox.token']") and g.locator("#fab").is_visible(), "conectado: token salvo, chat da IA aparece")
    g.reload()
    g.wait_for_selector("#nav .fold")
    ok(g.locator("#app").is_visible(), "continua logado no PC depois de recarregar (token)")
    ok(g.locator(".pcok").is_visible(), "selo de PC conectado na lateral")
    do_pc = g.evaluate("JSON.parse(localStorage['dumpbox.copia']).itens.length")
    g.evaluate("window.DUMPBOX_DESCONECTAR()")
    g.wait_for_selector("#nav .fold")
    loc = g.evaluate("JSON.parse(localStorage['dumpbox.local']).itens")
    ok(do_pc and any(i["titulo"] == "Pagar boleto" for i in loc) and not g.evaluate("localStorage['dumpbox.pc']"),
       "desconectar leva a cópia do PC para o aparelho (cards não somem)")
    antes = g.evaluate("localStorage['dumpbox.local']")
    g.goto(URL + "&demo=1")
    g.wait_for_selector("#nav .fold")
    g.wait_for_timeout(800)
    ok(g.evaluate("JSON.parse(localStorage['dumpbox.demo']).itens.length") == 7 and g.evaluate("localStorage['dumpbox.local']") == antes, "demo mostra exemplos sem tocar nos seus dados")
    ok(not erros, f"sem erros no console/rede {erros[:3]}")
    b.close()
srv.shutdown()
pc.terminate()
print("FALHAS:", falhas if falhas else "nenhuma")
sys.exit(1 if falhas else 0)
