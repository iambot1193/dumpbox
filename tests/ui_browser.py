"""Testa a tela real (PC e celular) no Chrome headless, com banco temporário e dados sintéticos.
Não toca no banco do usuário. Fora do pytest: precisa de `pip install playwright` e do Chrome instalado.

    python tests/ui_browser.py [pasta_das_capturas]

Sai com código 1 se alguma verificação falhar. Caminho extra para o pacote: DUMPBOX_PW_PATH."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [p for p in (os.getenv("DUMPBOX_PW_PATH"), str(RAIZ / "backend")) if p]
HOME = tempfile.mkdtemp(prefix="dumpbox_ui_")
os.environ.update(DUMPBOX_HOME=HOME, DUMPBOX_WORKER="0", DUMPBOX_SECRET="teste-ui-segredo", DUMPBOX_NO_BROWSER="1")
from dumpbox import auth, db  # noqa: E402

os.environ["DUMPBOX_PASSWORD_HASH"] = auth.hash_senha("senha-de-teste")
SAIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="dumpbox_ui_capturas_"))
SAIDA.mkdir(exist_ok=True)
PORTA = 8123
URL = f"http://127.0.0.1:{PORTA}"

c = db.conectar()
c.execute("INSERT INTO captura(id,texto,criado_em,status) VALUES('seed','x','2026-01-01','ok')")
h = datetime.now()
d = lambda n, hora="": (h + timedelta(days=n)).strftime("%Y-%m-%d") + hora
ITENS = [
    ("tarefa", "Enviar nota fiscal de outubro", "trabalho", d(-2), "alta"),
    ("tarefa", "Revisar proposta do cliente", "trabalho", d(0, "T17:00"), "alta"),
    ("compromisso", "Reunião de alinhamento", "trabalho", d(2, "T10:00"), "media"),
    ("tarefa", "Atualizar planilha de horas", "trabalho", d(3), "baixa"),
    ("ideia", "Modelo de proposta reutilizável", "trabalho", None, "baixa"),
    ("compra", "Comprar suporte de notebook", "trabalho", None, "baixa"),
    ("compromisso", "Agendar exame periódico", "trabalho", d(6, "T08:00"), "media"),
    ("compromisso", "Consulta de retorno", "saude", d(0, "T14:00"), "alta"),
    ("tarefa", "Pagar conta de luz", "financas", d(0), "alta"),
    ("compra", "Comprar café e pão", "casa", None, "baixa"),
]
ids = {}
for tipo, titulo, ctx, prazo, prio in ITENS:
    ids[titulo] = c.execute("INSERT INTO item(captura_id,tipo,titulo,contexto,prazo_em,prioridade,estado,criado_em) VALUES('seed',?,?,?,?,?,'catalogado','2026-01-01')",
                            (tipo, titulo, ctx, prazo, prio)).lastrowid
c.execute("INSERT INTO item(captura_id,tipo,titulo,contexto,prioridade,estado,criado_em) VALUES('seed','tarefa','Ligar p/ seguradora','financas','baixa','arquivado','2026-01-01')")
c.execute("INSERT INTO item(captura_id,tipo,titulo,contexto,prioridade,estado,criado_em) VALUES('seed','tarefa','Enviar relatório mensal','trabalho','baixa','feito','2026-01-01')")
c.execute("INSERT INTO captura(id,texto,criado_em,status,erro) VALUES('rev1','ver aquele negócio de terça','2026-01-01','falhou','ValidationError')")
c.commit()
item = lambda t: c.execute("SELECT * FROM item WHERE titulo=?", (t,)).fetchone()

srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "dumpbox.api:app", "--port", str(PORTA), "--log-level", "warning"],
                       cwd=RAIZ, env={**os.environ, "PYTHONPATH": str(RAIZ / "backend")})
falhas = []


def ok(cond, nome):
    print(("ok   " if cond else "FALHA"), nome, flush=True)
    if not cond:
        falhas.append(nome)


from playwright.sync_api import sync_playwright  # noqa: E402

try:
    import httpx
    for _ in range(60):
        try:
            httpx.get(URL + "/api/estado", timeout=1)
            break
        except Exception:
            time.sleep(.5)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1500, "height": 950}, service_workers="block")
        ctx.add_init_script("localStorage.setItem('dumpbox.tour', '1')")  # tutorial do 1º acesso: testado no ui_local.py
        # avisos já permitidos; a notificação fica registrada em vez de aparecer
        ctx.add_init_script("""window.__avisos = []; window.Notification = class { static permission = 'granted';
          static requestPermission() { return Promise.resolve('granted'); } constructor(t, o) { window.__avisos.push([t, o.body]); } }""")
        g = ctx.new_page()
        erros = []
        g.on("pageerror", lambda e: erros.append(str(e)))
        g.on("response", lambda r: erros.append("404 " + r.url) if r.status == 404 else None)
        g.on("console", lambda m: erros.append(m.text) if m.type == "error" and "401" not in m.text and "422" not in m.text else None)  # 422 = data inválida do teste
        g.goto(URL)
        g.fill("#senha", "senha-de-teste")
        g.click("#entrar")
        g.wait_for_selector("#nav .fold")
        g.wait_for_selector("text=ATRASADOS")
        ok(g.locator(".sec").all_inner_texts() == ["ATRASADOS · 1", "HOJE · 3"], "Hoje junta atrasados e prazos do dia")
        ok(g.locator(".chip", has_text="atrasado 2 dias").count() == 1, "etiqueta atrasado")
        ok(g.evaluate("document.fonts.check('500 16px Barlow')"), "fonte própria carregou")
        g.screenshot(path=SAIDA / "1-hoje.png")
        g.wait_for_function("window.__avisos.length > 0", timeout=4000)
        av = g.evaluate("window.__avisos")
        ok(len(av) == 1 and "vencida" in av[0][0] and "•" in av[0][1], f"aviso de tarefa vencida {av}")
        time.sleep(5.5)
        ok(g.evaluate("window.__avisos.length") == 1, "não repete o aviso a cada atualização")
        ok(g.locator("#nav button", has_text="ligar avisos").count() == 0, "com avisos permitidos, some o “ligar avisos”")

        # Ctrl+V de um print (Win+Shift+S): vira captura de imagem na fila
        lista = base64.b64encode((RAIZ / "data" / "public" / "imagens" / "lista_01.png").read_bytes()).decode()  # checklist sintético
        g.evaluate("""async b64 => {
          const blob = await (await fetch('data:image/png;base64,' + b64)).blob();
          const dt = new DataTransfer(); dt.items.add(new File([blob], 'print.png', { type: 'image/png' }));
          document.getElementById('txt').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
        }""", lista)
        g.wait_for_selector("#anexo:not([hidden]) img")
        foto_na_fila = "fetch('/api/itens').then(r => r.json()).then(d => d.revisar.some(c => c.texto.includes('foto')))"
        ok(not g.evaluate(foto_na_fila), "Ctrl+V só anexa a foto (miniatura), não envia sozinho")
        g.fill("#txt", "tudo do trabalho")
        g.screenshot(path=SAIDA / "1b-foto-anexada.png")
        g.click("#guardar")
        g.wait_for_function(foto_na_fila.replace("includes('foto')", "includes('foto aguardando a IA: tudo do trabalho')"), timeout=5000)
        ok(g.locator("#anexo").is_hidden() and g.input_value("#txt") == "", "Guardar envia foto + instrução e limpa a caixa")

        g.click('[data-alvo="trabalho"]')
        g.wait_for_selector("h2:text-is('Trabalho')")
        card = lambda t: g.locator("#vista article", has=g.locator(f'h3:text-is("{t}")'))
        est = lambda t: card(t).evaluate("e=>[e.style.gridColumn,e.style.gridRow]")
        ok(card("Enviar relatório mensal").count() == 0, "feitos escondidos")
        g.click("text=Mostrar feitos (1)")
        ok(card("Enviar relatório mensal").count() == 1, "Mostrar feitos")
        g.click("text=Mostrar feitos (1)")

        # livre: solta numa célula distante, deixando buraco
        t = "Comprar suporte de notebook"
        caixa = card(t).bounding_box()
        grade = g.locator(".grid").bounding_box()
        largc = (grade["width"] - 36) / 4
        destino = (grade["x"] + 3 * (largc + 12) + 20, grade["y"] + 4 * 140 + 20)
        g.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
        g.mouse.down()
        g.mouse.move(caixa["x"] + caixa["width"] / 2 + 30, caixa["y"] + caixa["height"] / 2 + 30, steps=3)
        g.mouse.move(*destino, steps=8)
        ok(g.locator(".ph").count() == 1, "mostra onde o card vai cair")
        g.screenshot(path=SAIDA / "2-arraste.png")
        g.mouse.up()
        ok(card(t).evaluate("e=>e.style.gridColumnStart") == "4", "card foi para a coluna 4")
        time.sleep(.4)
        ok((item(t)["grade_col"], item(t)["grade_lin"]) == (4, 5), f"posição salva {item(t)['grade_col']},{item(t)['grade_lin']}")
        g.reload(); g.wait_for_selector("h2:text-is('Trabalho')")
        ok(card(t).evaluate("e=>e.style.gridColumnStart") == "4", "posição continua depois de recarregar")

        # sobre outro card: o outro desce, ninguém sobrepõe
        t2 = "Atualizar planilha de horas"
        alvo = card("Reunião de alinhamento").bounding_box()
        caixa = card(t2).bounding_box()
        g.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2); g.mouse.down()
        g.mouse.move(alvo["x"] + 20, alvo["y"] + 20, steps=8); g.mouse.up()
        time.sleep(.3)
        ret = g.eval_on_selector_all("#vista article", "a=>a.map(e=>{const r=e.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom]})")
        sobre = any(a[0] < b_[2] - 1 and b_[0] < a[2] - 1 and a[1] < b_[3] - 1 and b_[1] < a[3] - 1 for i, a in enumerate(ret) for b_ in ret[i + 1:])
        ok(not sobre, "nenhum card sobreposto depois de soltar em cima de outro")

        # aumentar pelo canto
        t3 = g.evaluate("""[...document.querySelectorAll('#vista article')].find(e=>+e.style.gridColumnStart<=3 && !e.classList.contains('w2')).querySelector('h3').textContent""")
        print("redimensiona:", t3)
        card(t3).hover()
        al = card(t3).locator(".rs").bounding_box()
        antes = card(t3).bounding_box()
        g.mouse.move(al["x"] + 10, al["y"] + 10); g.mouse.down()
        g.mouse.move(antes["x"] + antes["width"] + largc * .9, antes["y"] + antes["height"] + 150, steps=8)
        ok(card(t3).locator(".tamanho").inner_text() == "2 × 2", "mostra o tamanho enquanto segura")
        ok(g.locator(".grid.guias").count() == 1, "grade de fundo aparece enquanto segura")
        ret = g.eval_on_selector_all("#vista article", "a=>a.map(e=>{const r=e.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom]})")
        ok(not any(a[0] < b_[2] - 1 and b_[0] < a[2] - 1 and a[1] < b_[3] - 1 and b_[1] < a[3] - 1 for i, a in enumerate(ret) for b_ in ret[i + 1:]),
           "prévia já afasta os outros cards (nada por baixo)")
        g.screenshot(path=SAIDA / "13-redimensionar.png")
        g.mouse.up()
        ok(g.locator(".tamanho").count() == 0 and g.locator(".grid.guias").count() == 0, "etiqueta e grade somem ao soltar")
        time.sleep(.4)
        ok(item(t3)["grade_alt"] == 2 and item(t3)["grade_larg"] == 2, f"tamanho salvo {item(t3)['grade_larg']}x{item(t3)['grade_alt']} na coluna {item(t3)['grade_col']}")
        g.mouse.move(5, 5)
        g.screenshot(path=SAIDA / "3-pasta.png", full_page=True)

        # criticidade + filtro
        t4 = "Reunião de alinhamento"
        card(t4).locator(".sig").click()
        ok(g.locator(".menu h6").inner_text() == "Criticidade", "menu de criticidade abre")
        g.locator(".menu button", has_text="crítica").click()
        g.wait_for_selector("article.critica")
        ok(item(t4)["prioridade"] == "critica", "crítica salva")
        ok(g.locator("#toast", has_text="agora é crítica").count() == 1, "aviso com Desfazer")
        g.locator(".ft button", has_text="crítica").click()
        ok(g.locator("#vista article").count() == 1, "filtro por criticidade")
        g.locator(".ft button", has_text="Todas").click()

        # arrastar para pasta + desfazer
        t5 = "Agendar exame periódico"
        caixa = card(t5).bounding_box()
        pasta = g.locator('[data-alvo="saude"]').bounding_box()
        g.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2); g.mouse.down()
        g.mouse.move(pasta["x"] + 50, pasta["y"] + 20, steps=8)
        ok("over" in g.locator('[data-alvo="saude"]').get_attribute("class"), "pasta acende como alvo")
        g.mouse.up()
        g.wait_for_selector("#toast >> text=foi para Saúde")
        ok(item(t5)["contexto"] == "saude", "arraste para pasta muda a pasta")
        g.click("#toast button")
        time.sleep(.5)
        ok(item(t5)["contexto"] == "trabalho", "Desfazer devolve")

        # mover pelo menu; excluir; lixeira
        g.wait_for_selector(f'h3:text-is("{t5}")')
        card(t5).hover()
        card(t5).locator("button[aria-label='Mover para…']").click()
        g.locator(".menu button", has_text="Estudos").click()
        g.wait_for_selector("#toast >> text=foi para Estudos")
        ok(item(t5)["contexto"] == "estudos", "Mover para…")
        t6 = "Comprar suporte de notebook"
        card(t6).hover()
        card(t6).locator("button[aria-label='Excluir']").click()
        g.wait_for_selector("#toast >> text=foi para a Lixeira")
        ok(item(t6)["estado"] == "arquivado", "Excluir vai para a Lixeira")
        g.click('[data-alvo="lixeira"]')
        g.wait_for_selector("h2:text-is('Lixeira')")
        linha = lambda t: g.locator(".lx", has=g.locator(f'h3:text-is("{t}")'))
        linha(t6).locator("button", has_text="Restaurar").click()
        time.sleep(.5)
        ok(item(t6)["estado"] == "catalogado", "Restaurar")
        linha("Ligar p/ seguradora").locator("button", has_text="Apagar de vez").click()
        g.wait_for_selector(".dlg")
        g.screenshot(path=SAIDA / "4-lixeira.png")
        g.locator(".dlg .no").click()
        ok(item("Ligar p/ seguradora") is not None, "Cancelar não apaga")
        linha("Ligar p/ seguradora").locator("button", has_text="Apagar de vez").click()
        g.locator(".dlg .si").click()
        time.sleep(.5)
        ok(item("Ligar p/ seguradora") is None, "Apagar de vez apaga")

        # Revisar, captura, IA
        g.locator(".fold", has_text="Revisar").click()
        g.wait_for_selector("text=ver aquele negócio de terça")
        ok(g.locator("button", has_text="Tentar de novo").count() == 1, "Revisar vira pasta")
        g.fill("#txt", "linha um\nlinha dois\nlinha tres\nlinha quatro")
        ok(g.evaluate("(()=>{const t=document.getElementById('txt');t.dispatchEvent(new Event('input'));return t.offsetHeight>80})()"), "caixa cresce")
        g.press("#txt", "Control+Enter")
        g.wait_for_selector("#st >> text=processando 1 nota")
        ok(g.input_value("#txt") == "", "Ctrl+Enter guarda")

        g.route("**/api/chat", lambda r: r.fulfill(json={"resposta": "Feito.", "feitas": ["“Pagar conta de luz” foi para Casa"], "grupo": "grupo-teste-1"}))
        g.click("#fab")
        g.fill("#cmsg", "move a luz para casa")
        g.press("#cmsg", "Enter")
        g.wait_for_selector("#msgs .undo")
        ok(g.locator(".res p").inner_text().endswith("foi para Casa"), "IA mostra o que fez")
        g.click('[data-alvo="trabalho"]')
        g.wait_for_selector("h2:text-is('Trabalho')")
        g.screenshot(path=SAIDA / "5-ia.png")
        # ---- seleção múltipla ----
        g.reload(); g.wait_for_selector("h2:text-is('Trabalho')")
        g.mouse.move(5, 5)
        tit = g.eval_on_selector_all("#vista article.c h3", "a=>a.map(e=>e.textContent)")
        h3 = lambda t: card(t).locator("h3")
        h3(tit[0]).click(modifiers=["Control"]); h3(tit[2]).click(modifiers=["Control"])
        ok(g.locator("#barra .n").inner_text() == "2 selecionados", "Ctrl+clique seleciona vários")
        h3(tit[4]).click(modifiers=["Shift"])
        ok(g.locator("#vista article.sel").count() == 3, "Shift+clique seleciona o intervalo")
        g.screenshot(path=SAIDA / "9-selecao.png")
        antes_crit = {t: item(t)["prioridade"] for t in tit[2:5]}
        g.locator("#barra button", has_text="Criticidade").click()
        ok(g.locator(".menu h6").inner_text() == "Criticidade de 3 itens", "menu em lote")
        g.locator(".menu button", has_text="crítica").click()
        g.wait_for_selector("#toast >> text=agora são crítica")
        ok(all(item(t)["prioridade"] == "critica" for t in tit[2:5]), "criticidade aplicada nos 3")
        ok(g.locator("#barra").is_hidden(), "seleção some depois da ação")
        g.click("#toast button")
        time.sleep(.6)
        ok({t: item(t)["prioridade"] for t in tit[2:5]} == antes_crit, "um Desfazer volta os 3 ao que eram")
        g.wait_for_selector("#vista article.c")
        # clique simples marca um; Shift+clique completa o intervalo (como no Explorer)
        g.wait_for_selector("#vista article.c")
        tit = g.eval_on_selector_all("#vista article.c h3", "a=>a.map(e=>e.textContent)")
        h3(tit[1]).click()
        ok(g.locator("#vista article.sel").count() == 1, "clique simples marca um card")
        h3(tit[4]).click(modifiers=["Shift"])
        ok(g.locator("#vista article.sel").count() == 4, "clique + Shift+clique marca o intervalo")
        h3(tit[1]).click(); h3(tit[1]).click()
        ok(g.locator("#vista article.sel").count() == 0, "clicar de novo no único marcado desmarca")
        card(tit[0]).hover(); card(tit[0]).locator("button.ed").click()
        ok(g.locator("form.dlg h4").inner_text() == "Editar" and g.locator("form.dlg input").first.input_value() == tit[0],
           "botão Editar abre o card preenchido")
        g.keyboard.press("Escape")
        # pincel: Shift + segurar sobre um card e passar o mouse marca os cards por onde passou, sem mover nada
        centro = lambda t: (lambda b: (b["x"] + b["width"] / 2, b["y"] + 20))(card(t).bounding_box())
        pos_antes = {t: (item(t)["grade_col"], item(t)["grade_lin"]) for t in tit}
        g.keyboard.down("Shift")
        g.mouse.move(*centro(tit[0])); g.mouse.down()
        for t in (tit[1], tit[3]):
            g.mouse.move(*centro(t), steps=6)
        g.mouse.up(); g.keyboard.up("Shift")
        marcados = set(g.eval_on_selector_all("#vista article.sel h3", "a=>a.map(e=>e.textContent)"))
        ok({tit[0], tit[1], tit[3]} <= marcados, f"Shift+arrastar marca os cards por onde passou ({len(marcados)})")
        ok({t: (item(t)["grade_col"], item(t)["grade_lin"]) for t in tit} == pos_antes, "Shift+arrastar não move cards")
        # começando num card já marcado, o gesto desmarca
        g.keyboard.down("Shift")
        g.mouse.move(*centro(tit[1])); g.mouse.down()
        g.mouse.move(*centro(tit[3]), steps=6)
        g.mouse.up(); g.keyboard.up("Shift")
        marcados2 = set(g.eval_on_selector_all("#vista article.sel h3", "a=>a.map(e=>e.textContent)"))
        ok(tit[0] in marcados2 and not {tit[1], tit[3]} & marcados2, f"Shift+arrastar a partir de marcado desmarca ({len(marcados2)})")
        g.keyboard.press("Escape")
        # laço: segurar no espaço vazio e arrastar
        grade = g.locator(".grid").bounding_box()
        rs = g.eval_on_selector_all("#vista article.c", "a=>a.map(e=>{const r=e.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom]})")
        x0, y0 = grade["x"] - 14, grade["y"] - 6  # no padding, fora de qualquer card
        alvo2 = rs[1]
        g.mouse.move(x0, y0); g.mouse.down()
        g.mouse.move(alvo2[0] + 30, alvo2[1] + 30, steps=8)
        ok(g.locator(".laco").count() == 1, "laço aparece ao arrastar no vazio")
        esperado = sum(1 for r in rs if r[0] < alvo2[0] + 30 and r[2] > x0 and r[1] < alvo2[1] + 30 and r[3] > y0)
        g.screenshot(path=SAIDA / "12-laco.png")
        g.mouse.up()
        ok(g.locator(".laco").count() == 0 and g.locator("#vista article.sel").count() == esperado >= 2, f"laço marca os cards tocados ({esperado})")
        vazio = g.locator("#vista").bounding_box()
        g.click("#vista h2")  # área vazia da página (não é card nem botão)
        ok(g.locator("#vista article.sel").count() == 0, "clique no vazio limpa")
        g.keyboard.press("Control+a")
        ok(g.locator("#vista article.sel").count() == g.locator("#vista article.c").count() > 3, "Ctrl+A seleciona todos")
        g.keyboard.press("Escape")
        ok(g.locator("#vista article.sel").count() == 0, "Esc limpa a seleção")
        # arrastar um selecionado leva o grupo
        tit = g.eval_on_selector_all("#vista article.c h3", "a=>a.map(e=>e.textContent)")
        a1, a2 = tit[1], tit[3]
        h3(a1).click(modifiers=["Control"]); h3(a2).click(modifiers=["Control"])
        caixa = h3(a1).bounding_box(); destino = g.locator('[data-alvo="casa"]').bounding_box()
        g.mouse.move(caixa["x"] + 20, caixa["y"] + 8); g.mouse.down()
        g.mouse.move(destino["x"] + 40, destino["y"] + 20, steps=10)
        ok(g.locator(".drag .qtd").inner_text() == "2", "arraste mostra quantos vão")
        g.mouse.up()
        g.wait_for_selector("#toast >> text=2 itens foram para Casa")
        ok(item(a1)["contexto"] == item(a2)["contexto"] == "casa", "arraste move a seleção inteira")
        g.click("#toast button"); time.sleep(.6)
        ok(item(a1)["contexto"] == "trabalho", "Desfazer do arraste em grupo")
        # Delete manda para a Lixeira (reversível)
        g.wait_for_selector(f'h3:text-is("{a1}")')
        h3(a1).click(modifiers=["Control"])
        g.keyboard.press("Delete")
        g.wait_for_selector("#toast >> text=foi para a Lixeira")
        ok(item(a1)["estado"] == "arquivado", "Delete exclui a seleção")
        g.click("#toast button"); time.sleep(.6)
        # ---- nova tarefa à mão ----
        # Rápida abre a linha: Enter cria e a linha fica pronta (com foco) para a próxima; "@" põe prazo
        g.click(".brapida")
        g.fill(".rapida input", "Rápida um @ amanhã 9h"); g.press(".rapida input", "Enter")
        g.wait_for_selector("#toast >> text=criado em")
        g.fill(".rapida input", "Rápida dois"); g.press(".rapida input", "Enter")
        g.wait_for_function("() => [...document.querySelectorAll('#vista h3')].some(h => h.textContent === 'Rápida dois')")
        r1, r2 = item("Rápida um"), item("Rápida dois")
        ok(r1 and r1["prazo_em"].endswith("T09:00") and r2 and r2["contexto"] == r1["contexto"], "criação rápida: Enter cria, @ põe prazo")
        ok(g.evaluate("document.activeElement === document.querySelector('.rapida input') && document.querySelector('.rapida input').value === ''"), "linha rápida continua com foco depois do redesenho")
        # check-list no texto do card: marcar grava no texto e conta
        g.evaluate("([id, d]) => api(`/api/itens/${id}/editar`, { mudancas: { detalhe: d } }).then(() => { ultimo = ''; return atualizar(); })", [r2["id"], "[ ] pão\n[x] leite\nobs"])
        cl = card("Rápida dois")
        ok(cl.locator(".det .cont").inner_text() == "☑ 1/2" and cl.locator(".chk input").count() == 2, "linhas [ ] viram check-list com contador")
        cl.locator(".chk input").first.click()
        g.wait_for_function("() => [...document.querySelectorAll('.det .cont')].some(e => e.textContent === '☑ 2/2')")
        ok(item("Rápida dois")["detalhe"] == "[x] pão\n[x] leite\nobs" and item("Rápida dois")["estado"] == "catalogado" and not card("Rápida dois").evaluate("e => e.classList.contains('sel')"),
           "marcar item grava no texto, sem concluir nem selecionar o card")
        g.click(".rapida .mais")
        g.fill(".nova input >> nth=0", "Preparar slides da aula")
        # check-list no formulário: um campo por item, Enter cria o próximo, Backspace no vazio apaga
        g.click(".nova .addli"); g.keyboard.type("slide 1"); g.keyboard.press("Enter"); g.keyboard.type("slide 2")
        g.keyboard.press("Enter"); g.keyboard.press("Backspace")
        ok(g.locator(".nova .li").count() == 2, "Enter cria item, Backspace no vazio apaga")
        g.fill(".nova input[placeholder^='ex.: sexta']", "quando der")
        g.click(".nova .si")
        g.wait_for_selector(".nova .erro >> text=não entendi a data")
        ok(g.locator(".nova").count() == 1, "data inválida mostra erro e mantém o formulário")
        g.fill(".nova input[placeholder^='ex.: sexta']", "amanhã 10h")
        g.screenshot(path=SAIDA / "10-nova.png")
        g.press(".nova input[placeholder^='ex.: sexta']", "Enter")
        g.wait_for_selector("#toast >> text=criado em Trabalho")
        novo_ = item("Preparar slides da aula")
        ok(novo_ is not None and novo_["contexto"] == "trabalho" and novo_["prazo_em"].endswith("T10:00") and novo_["prioridade"] == "alta",
           "nova tarefa criada na pasta atual, com prazo e prioridade por regra")
        ok(card("Preparar slides da aula").count() == 1, "nova tarefa aparece na tela")
        ok(novo_["detalhe"] == "[ ] slide 1\n[ ] slide 2", f"check-list do formulário grava no texto {novo_['detalhe']!r}")
        card("Preparar slides da aula").hover(); card("Preparar slides da aula").locator(".ed").click()
        ok(g.locator(".nova .li").count() == 2 and g.locator(".nova textarea").input_value() == "", "Editar abre com os itens da check-list")
        g.keyboard.press("Escape")
        g.click(".bnova")
        ok(g.locator(".nova h4").inner_text() == "Nova tarefa", "+ Nova abre o formulário completo (Rápida é outro botão)")
        g.keyboard.press("Escape")
        # ---- pastas: criar, usar, apagar ----
        g.keyboard.press("Escape")
        g.click(".fold.mais")
        g.fill(".nova input >> nth=0", "Projetos Pessoais")
        g.fill(".nova input >> nth=1", "site pessoal, side projects")
        g.press(".nova input >> nth=1", "Enter")
        g.wait_for_selector("h2:text-is('Projetos Pessoais')")
        ok(g.locator('[data-alvo="projetos_pessoais"]').count() == 1, "pasta nova aparece na lateral e abre")
        g.click(".fold.mais")
        g.fill(".nova input >> nth=0", "projetos pessoais")
        g.press(".nova input >> nth=0", "Enter")
        g.wait_for_selector(".nova .erro >> text=já existe")
        ok(True, "nome repetido mostra erro")
        g.keyboard.press("Escape")
        g.click('[data-alvo="trabalho"]'); g.wait_for_selector("h2:text-is('Trabalho')")
        tp = "Revisar proposta do cliente"
        card(tp).hover(); card(tp).locator("button[aria-label='Mover para…']").click()
        g.locator(".menu button", has_text="Projetos Pessoais").click()
        g.wait_for_selector("#toast >> text=foi para Projetos Pessoais")
        ok(item(tp)["contexto"] == "projetos_pessoais", "mover para pasta nova")
        g.click('[data-alvo="projetos_pessoais"]'); g.wait_for_selector("h2:text-is('Projetos Pessoais')")
        g.screenshot(path=SAIDA / "14-pasta-nova.png")
        g.locator("button", has_text="Apagar pasta").click()
        g.wait_for_selector(".nova select")
        g.select_option(".nova select", "casa")
        g.screenshot(path=SAIDA / "15-apagar-pasta.png")
        g.click(".nova .si")
        g.wait_for_selector("#toast >> text=Pasta “Projetos Pessoais” apagada")
        g.wait_for_function("!document.querySelector('[data-alvo=\"projetos_pessoais\"]')", timeout=8000)
        ok(item(tp)["contexto"] == "casa" and g.locator('[data-alvo="projetos_pessoais"]').count() == 0, "apagar pasta move os itens e some da lateral")
        g.click('[data-alvo="outro"]'); g.wait_for_selector("h2:text-is('Outro')")
        ok(g.locator("button", has_text="Apagar pasta").count() == 0, "Outro não tem Apagar pasta")
        ok(g.evaluate("document.documentElement.scrollWidth<=innerWidth"), "sem rolagem horizontal no PC")
        # cópia para o celular pela tela do PC; ditado e busca
        with g.expect_download() as dl:
            g.click("#nav button:has-text('mais')"); g.click(".menu button:has-text('Cópia p/ celular')")
        ok(dl.value.suggested_filename.startswith("copia-celular-") and json.loads(Path(dl.value.path()).read_text(encoding="utf-8"))["dumpbox"] == 1,
           "botão baixa a cópia para o celular")
        ok(g.locator("#voz").is_visible(), "botão de ditado (Chrome tem reconhecimento de voz)")
        g.fill("#busca", "reuniao")
        g.wait_for_selector("h2:text-is('Busca')")
        ok(g.locator("#vista article.c h3").all_inner_texts() == ["Reunião de alinhamento"], "busca sem acento acha “Reunião”")
        g.click('[data-alvo="casa"]')
        ok(g.input_value("#busca") == "" and g.locator("h2:text-is('Casa')").count() == 1, "trocar de pasta limpa a busca")

        # Editar: texto abaixo do título e prazo pelo calendário (dia + hora); apagar o dia tira o prazo
        te = g.locator("#vista article.c h3").first.inner_text()
        card(te).hover(); card(te).locator("button.ed").click()
        g.fill("form.dlg textarea", "ligar antes\nlevar documentos")
        g.fill("form.dlg input[type=date]", "2026-12-10"); g.fill("form.dlg input[type=time]", "14:30")
        g.click(".nova .si"); g.wait_for_selector("form.dlg", state="detached"); time.sleep(.4)
        ok(item(te)["detalhe"] == "ligar antes\nlevar documentos" and item(te)["prazo_em"] == "2026-12-10T14:30", "Editar grava texto e prazo do calendário")
        ok(card(te).locator(".det").inner_text().startswith("ligar antes"), "texto aparece abaixo do título")
        g.screenshot(path=SAIDA / "16-texto-no-card.png")
        card(te).hover(); card(te).locator("button.ed").click()
        ok(g.input_value("form.dlg input[type=date]") == "2026-12-10" and g.input_value("form.dlg input[type=time]") == "14:30", "Editar abre com o dia e a hora do prazo")
        g.fill("form.dlg input[type=date]", "")
        g.click(".nova .si"); g.wait_for_selector("form.dlg", state="detached"); time.sleep(.4)
        ok(item(te)["prazo_em"] is None, "apagar o dia tira o prazo")
        # copiar (Ctrl+C na seleção) e Colar: o texto volta a virar cards iguais
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=URL)
        tc = g.eval_on_selector_all("#vista article.c h3", "a=>a.map(e=>e.textContent)")[:2]
        for t in tc: h3(t).click(modifiers=["Control"])
        g.keyboard.press("Control+c")
        g.wait_for_selector("#toast >> text=2 cards copiados")
        clip = g.evaluate("navigator.clipboard.readText()").replace("\r\n", "\n")  # Windows devolve \r\n
        ok(clip.startswith("*Casa*\n") and all(f"☐ {t}\n    _" in clip for t in tc), f"Ctrl+C copia os selecionados como lista para WhatsApp {clip!r}")
        g.keyboard.press("Escape")
        g.click(".bcolar")
        g.wait_for_selector("#toast >> text=2 cards colados")
        conta = lambda t: c.execute("SELECT count(*) FROM item WHERE titulo=? AND estado!='arquivado'", (t,)).fetchone()[0]
        copias = [c.execute("SELECT * FROM item WHERE titulo=? ORDER BY id DESC", (t,)).fetchone() for t in tc]
        ok(all(conta(t) == 2 for t in tc) and all(x["contexto"] == "casa" for x in copias), "Colar cria os cards copiados")
        ok(any(x["detalhe"] == "ligar antes\nlevar documentos" for x in copias) if te in tc else True, "texto do card vai junto na cópia")
        # Ctrl+V de texto qualquer fora da caixa: um card por linha, etiqueta do dumpbox lida
        g.evaluate("""() => { const dt = new DataTransfer(); dt.setData('text/plain', '*Casa*\\n☐ Colado A\\n    _ideia · alta · 📅 01/12/2026 09:00_\\n    com detalhe\\n- [ ] Colado B (sem etiqueta)\\n✅ ~Colado C~');
          document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }""")
        g.wait_for_function("() => !/2 cards colados/.test(document.querySelector('#toast').innerText)", timeout=15000)
        ok("3 cards colados" in g.inner_text("#toast"), f"Ctrl+V cola 3 cards ({g.inner_text('#toast')})")
        A, B, C = item("Colado A"), item("Colado B (sem etiqueta)"), item("Colado C")
        ok(A and A["tipo"] == "ideia" and A["prioridade"] == "alta" and A["prazo_em"] == "2026-12-01T09:00" and A["detalhe"] == "com detalhe",
           "colar lê pasta, tipo, criticidade, prazo e texto")
        ok(B and B["contexto"] == "casa" and C and C["estado"] == "feito", "linha sem etiqueta vai para a pasta aberta; [x] entra feito")
        g.screenshot(path=SAIDA / "17-colado.png")

        ok(erros == [], f"console limpo {erros}")
        ctx.close()

        # celular: toque real pelo protocolo do Chrome
        ctx = b.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True, device_scale_factor=2, service_workers="block")
        ctx.add_init_script("localStorage.setItem('dumpbox.tour', '1')")
        m = ctx.new_page()
        erros2 = []
        m.on("pageerror", lambda e: erros2.append(str(e)))
        m.goto(URL)
        m.fill("#senha", "senha-de-teste")
        m.click("#entrar")
        m.wait_for_selector("#nav .fold")
        m.tap('[data-alvo="trabalho"]')
        m.wait_for_selector("h2:text-is('Trabalho')")
        ok(m.evaluate("document.documentElement.scrollWidth<=innerWidth"), "sem rolagem horizontal no celular")
        bx = m.locator("#vista article .acts .ok").first.bounding_box()
        ok(bx["width"] >= 44 and bx["height"] >= 44, "botões do celular com 44 px")
        ok(m.locator("#vista .rs:visible").count() > 0, "alça de tamanho no celular")
        larg_cards = m.eval_on_selector_all("#vista article.c", "a=>a.map(e=>Math.round(e.getBoundingClientRect().width))")
        ok(len(set(larg_cards)) == 2 and max(larg_cards) > 1.8 * min(larg_cards), f"celular em 2 colunas: meio e inteiro {sorted(set(larg_cards))}")
        m.screenshot(path=SAIDA / "6-celular.png")
        cdp = ctx.new_cdp_session(m)
        toque = lambda tipo, pts: cdp.send("Input.dispatchTouchEvent", {"type": tipo, "touchPoints": pts})
        # puxar o canto: direita = inteiro, para baixo = mais alto; grava na grade
        meio = m.locator("#vista article.c:not(.w2)").first
        tm = meio.locator("h3").inner_text()
        meio.evaluate("e => e.scrollIntoView({ block: 'center' })"); time.sleep(.2)
        rb = meio.locator(".rs").bounding_box()
        xr, yr = rb["x"] + 10, rb["y"] + 10
        toque("touchStart", [{"x": xr, "y": yr}])
        for i in range(1, 7):
            toque("touchMove", [{"x": xr + 12 * i, "y": yr + 18 * i}]); time.sleep(.03)
        ok("inteiro × 2" in m.inner_text("#vista .tamanho"), "prévia do tamanho ao puxar o canto")
        toque("touchEnd", [])
        m.wait_for_function(f"[...document.querySelectorAll('#vista article.c.w2 h3')].some(h => h.textContent === {tm!r})")
        time.sleep(.4)
        ok(item(tm)["grade_larg"] >= 2 and item(tm)["grade_alt"] == 2, "redimensionar no celular grava largura e altura")
        ok(m.locator("#barra").is_hidden() and m.locator(".drag").count() == 0, "puxar o canto não seleciona nem arrasta")
        t7 = "Atualizar planilha de horas"
        cx = m.locator("#vista article", has=m.locator(f'h3:text-is("{t7}")'))
        cx.scroll_into_view_if_needed()
        a = cx.locator(".meta").bounding_box()
        dst = m.locator('[data-alvo="financas"]').bounding_box()
        x0, y0 = a["x"] + 40, a["y"] + 10
        toque("touchStart", [{"x": x0, "y": y0}])
        time.sleep(.5)
        ok(m.locator(".drag").count() == 0 and m.locator("#barra .n").inner_text() == "1 selecionado", "segurar parado liga a seleção")
        toque("touchMove", [{"x": x0, "y": y0 + 20}]); time.sleep(.05)
        ok(m.locator(".drag").count() == 1 and m.locator("#vista article.sel").count() == 0, "segurar e mover arrasta (e desfaz a seleção)")
        n = 10
        for i in range(1, n + 1):
            toque("touchMove", [{"x": x0 + (dst["x"] + 30 - x0) * i / n, "y": y0 + (dst["y"] + 20 - y0) * i / n}])
            time.sleep(.03)
        ok("over" in m.locator('[data-alvo="financas"]').get_attribute("class"), "trilho acende no toque")
        m.screenshot(path=SAIDA / "7-celular-arraste.png")
        toque("touchEnd", [])
        m.wait_for_selector("#toast >> text=foi para Finanças", timeout=4000)
        ok(item(t7)["contexto"] == "financas", "arraste por toque move de pasta")

        # segurar e soltar em cima de outro card: os dois trocam de lugar (ordem da lista e grade salva)
        m.wait_for_function("!document.querySelector('#barra:not([hidden])')")
        hs = lambda: m.eval_on_selector_all("#vista article.c h3", "a=>a.map(e=>e.textContent)")
        ordem = hs()
        m.evaluate("scrollTo(0, 0)"); time.sleep(.2)
        c0 = m.locator("#vista article.c").nth(0).locator(".meta").bounding_box()
        c2 = m.locator("#vista article.c").nth(2).locator(".meta").bounding_box()
        x0, y0 = c0["x"] + 40, c0["y"] + 10
        toque("touchStart", [{"x": x0, "y": y0}]); time.sleep(.5)
        for i in range(1, 9):  # 2 colunas: o destino pode estar ao lado
            toque("touchMove", [{"x": x0 + (c2["x"] + 40 - x0) * i / 8, "y": y0 + (c2["y"] + 10 - y0) * i / 8}]); time.sleep(.03)
        ok("over" in (m.locator("#vista article.c").nth(2).get_attribute("class") or ""), "card de destino acende")
        m.screenshot(path=SAIDA / "7b-celular-trocar.png")
        toque("touchEnd", [])
        m.wait_for_function(f"document.querySelectorAll('#vista article.c h3')[2]?.textContent === {ordem[0]!r}")
        nova = hs()
        ok(nova[0] == ordem[2] and nova[2] == ordem[0], f"soltar em cima troca os dois de lugar {nova[:3]}")
        time.sleep(.4)
        m.reload(); m.wait_for_selector("h2:text-is('Trabalho')")
        ok(hs()[:3] == nova[:3], "ordem trocada continua depois de recarregar")

        # segurar um card e tocar em outros: seleciona vários
        cs = m.locator("#vista article.c")
        b0 = cs.nth(0).locator(".meta").bounding_box()
        toque("touchStart", [{"x": b0["x"] + 40, "y": b0["y"] + 10}]); time.sleep(.5); toque("touchEnd", [])
        time.sleep(.4)
        ok(m.locator("#barra .n").inner_text() == "1 selecionado", "segurar e soltar mantém o card selecionado")
        cs.nth(1).locator("h3").tap(); cs.nth(3).locator("h3").tap()
        ok(m.locator("#barra .n").inner_text() == "3 selecionados", "depois de segurar, toques somam à seleção")
        m.locator("#barra button.x").tap()

        # deslizar o card para a direita conclui (sem esperar segurar)
        cs = m.locator("#vista article.c")
        m.evaluate("scrollTo(0, 0)"); time.sleep(.2)
        tz = cs.nth(0).locator("h3").inner_text()
        bz = cs.nth(0).locator(".meta").bounding_box()
        xz, yz = bz["x"] + 20, bz["y"] + 10
        toque("touchStart", [{"x": xz, "y": yz}])
        for i in range(1, 7):
            toque("touchMove", [{"x": xz + 30 * i, "y": yz + 2}]); time.sleep(.02)
        ok("desliza" in (cs.nth(0).get_attribute("class") or ""), "card acompanha o dedo ao deslizar")
        ok(m.locator(".rastro.pronto").count() == 1 and "feito" in m.inner_text(".rastro"), "faixa “feito” aparece cheia ao passar do ponto")
        m.screenshot(path=SAIDA / "18-celular-deslizar.png")
        toque("touchEnd", [])
        m.wait_for_selector("#toast >> text=marcado como feito", timeout=4000)
        ok(item(tz)["estado"] == "feito", "deslizar para a direita marca como feito")
        ok(m.locator("#barra").is_hidden(), "deslizar não liga a seleção")
        # card meio é quase todo botão: deslizar começando em cima do botão de apagar também conclui (e não apaga)
        m.wait_for_function("!document.querySelector('#vista article.c[style*=\"translateX\"]')")
        cm = m.locator("#vista article.c:not(.w2)").first
        cm.evaluate("e => e.scrollIntoView({ block: 'center' })"); time.sleep(.2)
        tb = cm.locator("h3").inner_text()
        bb = cm.locator(".acts .tr").bounding_box()
        xb, yb = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
        toque("touchStart", [{"x": xb, "y": yb}])
        for i in range(1, 7):
            toque("touchMove", [{"x": xb + 20 * i, "y": yb + 2}]); time.sleep(.02)
        toque("touchEnd", [])
        m.wait_for_selector(f"#toast >> text=“{tb}” marcado como feito", timeout=4000)
        ok(item(tb)["estado"] == "feito", "deslizar começando no botão do card meio conclui sem apagar")

        # puxar o aviso para o lado fecha; menu "avisos" desliga o aviso ao concluir
        ta = m.locator("#toast span").bounding_box()
        xa, ya = ta["x"] + 10, ta["y"] + ta["height"] / 2
        toque("touchStart", [{"x": xa, "y": ya}])
        for i in range(1, 6):
            toque("touchMove", [{"x": xa + 25 * i, "y": ya}]); time.sleep(.02)
        toque("touchEnd", [])
        ok(m.locator("#toast").is_hidden(), "puxar o aviso para o lado fecha")
        m.locator("#nav button.mais.sair").scroll_into_view_if_needed(); time.sleep(1)  # toque com a lateral ainda rolando perde o clique
        m.locator("#nav button.mais.sair").tap(); time.sleep(.3)
        m.locator(".menu button", has_text="Avisos").tap(); time.sleep(.3)
        m.locator(".menu button", has_text="Ao concluir").tap()
        ok("Ao concluir: não" in m.inner_text(".menu"), "menu de avisos troca a opção e continua aberto")
        m.keyboard.press("Escape")
        m.evaluate("toast('teste', 'g-teste', 'concluir')")  # mesma chamada que concluir faz (sem gastar card)
        ok(m.locator("#toast").is_hidden(), "com “ao concluir” desligado, concluir não mostra aviso")
        m.evaluate("localStorage.removeItem('dumpbox.avisos')")

        # rolar não deve virar arraste
        a = m.locator("#vista article .meta").first.bounding_box()
        y1 = m.evaluate("scrollY")
        toque("touchStart", [{"x": a["x"] + 40, "y": 600}])
        for i in range(1, 8):
            toque("touchMove", [{"x": a["x"] + 40, "y": 600 - 30 * i}]); time.sleep(.02)
        toque("touchEnd", [])
        time.sleep(.4)
        ok(m.locator(".drag").count() == 0, "rolagem não inicia arraste")

        # seleção no celular: botão Selecionar + toques
        m.tap(".bsel")
        ok(m.locator("#barra .n").inner_text().startswith("Toque nos cards"), "modo Selecionar no celular")
        cs = m.locator("#vista article.c h3")
        t8, t9 = cs.nth(0).inner_text(), cs.nth(1).inner_text()
        cs.nth(0).tap(); cs.nth(1).tap()
        ok(m.locator("#barra .n").inner_text() == "2 selecionados", "toque seleciona no modo Selecionar")
        m.screenshot(path=SAIDA / "11-celular-selecao.png")
        m.locator("#barra button", has_text="Mover").tap()
        m.locator(".menu button", has_text="Estudos").tap()
        m.wait_for_selector("#toast >> text=2 itens foram para Estudos")
        ok(item(t8)["contexto"] == item(t9)["contexto"] == "estudos", "mover em lote no celular")
        m.route("**/api/chat", lambda r: r.fulfill(json={"resposta": "Feito.", "feitas": ["x foi para Casa", "y foi para Casa"], "grupo": "grupo-teste-2"}))
        m.tap("#fab")
        m.fill("#cmsg", "move")
        m.press("#cmsg", "Enter")
        m.wait_for_selector("#iamini >> text=2 feitas")
        ok(m.locator("#ia").is_hidden(), "IA encolhe para uma linha no celular")
        m.wait_for_timeout(9500)
        m.screenshot(path=SAIDA / "8-celular-ia.png")
        ok(erros2 == [], f"console limpo no celular {erros2}")
        b.close()
finally:
    srv.terminate()
    srv.wait(10)
print("FALHAS:", json.dumps(falhas, ensure_ascii=False), "| capturas em", SAIDA)
sys.exit(1 if falhas else 0)
