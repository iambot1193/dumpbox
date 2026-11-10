// PWA: fila local de capturas (localStorage) -> envia ao servidor quando houver conexão.
// Todo texto vindo do servidor entra via textContent (nunca innerHTML).
const $ = id => document.getElementById(id);
const FILA = "dumpbox.fila", VISTA = "dumpbox.vista";
const lerFila = () => { try { return JSON.parse(localStorage.getItem(FILA) || "[]"); } catch { return []; } };
const gravaFila = f => { try { localStorage.setItem(FILA, JSON.stringify(f)); } catch {} };
const uuid = () => crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);

// pastas vêm do servidor (o usuário cria e apaga); esta lista só vale até a primeira resposta
let PASTAS = [["casa", "Casa"], ["trabalho", "Trabalho"], ["freelance", "Freelance"], ["estudos", "Estudos"], ["saude", "Saúde"], ["financas", "Finanças"], ["outro", "Outro"]];
let NOME = Object.fromEntries(PASTAS);
const NIVEIS = [["critica", "crítica", 4], ["alta", "alta", 3], ["media", "média", 2], ["baixa", "baixa", 1]];
const SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
const COLS = 4, ALT_LIN = 128, GAP = 12;
const AREA_GRADE = "(hover:hover) and (min-width:761px)";

let D = { itens: [], revisar: [], lixeira: [] }, ultimo = "", vista = "hoje", verFeitos = false, filtro = null;
let gesto = false, menuAberto = null, dlgAberto = false, vistos = null, gradeAtual = null;
let sel = new Set(), ancora = null, modoSel = false, arrastou = false;  // seleção múltipla (Ctrl/Shift ou modo Selecionar)
const TIPOS = ["tarefa", "compromisso", "ideia", "compra", "nota"];
try { vista = localStorage.getItem(VISTA) || "hoje"; } catch {}

function el(tag, cls, txt) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  return e;
}
function ic(n) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"), u = document.createElementNS("http://www.w3.org/2000/svg", "use");
  s.setAttribute("class", "i"); u.setAttribute("href", "#" + n); s.append(u); return s;
}
function botao(cls, conteudo, rotulo, fn) {
  const b = el("button", cls);
  b.append(...conteudo);
  if (rotulo) { b.title = rotulo; b.setAttribute("aria-label", rotulo); }
  b.onclick = e => { e.stopPropagation(); fn(e); };
  return b;
}

async function api(url, body) {
  const r = await fetch(url, { method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (r.status === 401) { mostra("login"); throw new Error("401"); }
  if (!r.ok) {
    const e = new Error(r.status);
    e.detail = (await r.json().catch(() => ({}))).detail;
    throw e;
  }
  return r.json();
}
function mostra(tela) { for (const t of ["setup", "login", "app"]) $(t).hidden = tela !== t; }

// Barra de preparo da IA (1ª execução do exe: baixa o Ollama e o modelo). Notas já podem ser guardadas.
// o aviso fica fixo no topo: empurra a lateral e o conteúdo para não cobrir nada
const topo = () => requestAnimationFrame(() => document.documentElement.style.setProperty("--topo", $("prep").hidden ? "0px" : $("prep").offsetHeight + "px"));
async function estado() {
  try {
    const e = await (await fetch("/api/estado")).json();
    const p = e.preparo, b = $("prep");
    b.hidden = p.pronto; topo();
    if (!p.pronto) b.textContent = p.erro ? `Erro ao preparar a IA: ${p.erro}` : `Preparando a IA (só na primeira vez): ${p.msg || "aguarde"} ${p.pct ? p.pct + "%" : ""}`;
    return e;
  } catch {
    const b = $("prep"); b.hidden = false; topo();
    b.textContent = "Sem conexão com o servidor. O dumpbox.exe está aberto no PC? Suas notas ficam na fila e são enviadas quando ele voltar.";
    return null;
  }
}

function mostrarFila() {
  const q = lerFila().length, p = D.revisar.filter(c => c.status === "pendente").length, partes = [];
  if (p) partes.push(`processando ${p} nota${p > 1 ? "s" : ""}`);
  if (q) partes.push(`${q} na fila, aguardando o PC`);
  $("st").replaceChildren(...(partes.length ? [ic("spin"), partes.join(" · ")] : []));
}
async function enviarFila() {
  let fila = lerFila();
  for (const n of [...fila]) {
    try { await api("/api/capturas", n); fila = fila.filter(x => x.id !== n.id); gravaFila(fila); }
    catch (e) { if (String(e.message) === "401") return; break; }
  }
  mostrarFila();
}

// ---- datas ----
function partes(p) { return p.slice(0, 10).split("-").map(Number); }
function dias(p) {
  const [a, m, d] = partes(p), h = new Date();
  return Math.round((Date.UTC(a, m - 1, d) - Date.UTC(h.getFullYear(), h.getMonth(), h.getDate())) / 864e5);
}
function txtPrazo(p) {
  const n = dias(p), [a, m, d] = partes(p);
  const [hh, mm] = p.length > 10 ? p.slice(11, 16).split(":") : [];
  const hora = hh ? `${+hh}h${mm !== "00" ? mm : ""}` : "";
  const nome = n === 0 ? "hoje" : n === 1 ? "amanhã" : n > 1 && n < 7 ? SEMANA[new Date(a, m - 1, d).getDay()] : `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}`;
  return hora ? `${nome}, ${hora}` : nome;
}
const aberto = i => i.estado !== "feito";
const atrasado = i => aberto(i) && i.prazo_em && dias(i.prazo_em) < 0;
const pasta = i => NOME[i.contexto] ? i.contexto : "outro";  // pasta apagada ou desconhecida: Outro
const nivel = i => NIVEIS.find(n => n[0] === i.prioridade) || NIVEIS[3];
const urgencia = (a, b) => (a.prazo_em ? dias(a.prazo_em) : 1e6) - (b.prazo_em ? dias(b.prazo_em) : 1e6) || nivel(b)[2] - nivel(a)[2] || b.id - a.id;

// ---- grade livre: posição e tamanho em células; nada se sobrepõe ----
const tam = i => ({ larg: i.grade_larg || (nivel(i)[2] >= 3 ? 2 : 1), alt: i.grade_alt || 1 });
function arranjar(lista, fixo) {
  const ocup = new Set(), pos = new Map();
  const celulas = p => { const r = []; for (let l = p.lin; l < p.lin + p.alt; l++) for (let c = p.col; c < p.col + p.larg; c++) r.push(`${c},${l}`); return r; };
  const cabe = p => p.col + p.larg - 1 <= COLS && celulas(p).every(k => !ocup.has(k));
  const poe = (id, p) => { celulas(p).forEach(k => ocup.add(k)); pos.set(id, p); };
  const procura = (id, t, de) => { for (let lin = de; ; lin++) for (let col = 1; col <= COLS - t.larg + 1; col++) if (cabe({ ...t, col, lin })) return poe(id, { ...t, col, lin }); };
  if (fixo) poe(fixo.id, { col: fixo.col, lin: fixo.lin, larg: fixo.larg, alt: fixo.alt });
  const resto = lista.filter(i => !fixo || i.id !== fixo.id), empurrados = [];
  for (const i of resto.filter(i => i.grade_col).sort((a, b) => a.grade_lin - b.grade_lin || a.grade_col - b.grade_col)) {
    const p = { ...tam(i), col: i.grade_col, lin: i.grade_lin };
    if (cabe(p)) poe(i.id, p); else empurrados.push([i, p.lin]);  // dois cards na mesma célula: o de trás desce
  }
  for (const [i, de] of empurrados) procura(i.id, tam(i), de);
  for (const i of resto.filter(i => !i.grade_col).sort(urgencia)) procura(i.id, tam(i), 1);
  return pos;
}
function fixarGrade(fixo) {
  // ponytail: cards fora do filtro não entram na conta; se colidirem depois, arranjar() os desce
  const lista = gradeAtual, pos = arranjar(lista, fixo), itens = [];
  for (const i of lista) {
    const p = pos.get(i.id);
    Object.assign(i, { grade_col: p.col, grade_lin: p.lin, grade_larg: p.larg, grade_alt: p.alt });
    itens.push({ id: i.id, ...p });
  }
  ultimo = ""; render();
  api("/api/layout", { itens }).catch(() => toast("Não consegui salvar a posição."));
}

// ---- ações ----
async function editar(ids, campo, valor) {
  try {
    const r = await api("/api/itens/editar", { ids: [].concat(ids), campo, valor });
    if (r.grupo) { (vistos ||= new Set()).add(r.grupo); toast(r.descricao, r.grupo); }
    ultimo = ""; await atualizar();
  } catch (e) { if (String(e.message) !== "401") toast("Não consegui salvar. O PC está ligado?"); }
}
let timerToast;
function toast(txt, grupo) {
  const t = $("toast");
  t.replaceChildren(ic("check"), el("span", "", txt));
  if (grupo) t.append(botao("", [ic("undo"), "Desfazer"], null, async () => { t.hidden = true; await api("/api/desfazer", { grupo }); ultimo = ""; atualizar(); }));
  t.hidden = false;
  clearTimeout(timerToast); timerToast = setTimeout(() => { t.hidden = true; }, 9000);
}
function fecharMenu() { if (menuAberto) { menuAberto.remove(); menuAberto = null; } }
function popover(ancora, titulo, opcoes) {
  fecharMenu();
  const m = el("div", "menu");
  m.append(el("h6", "", titulo));
  for (const o of opcoes) {
    const b = el("button", o.atual ? "cur" : "", o.txt);
    if (o.atual) b.append(el("span", "", "atual"));
    else b.onclick = () => { fecharMenu(); o.fn(); };
    m.append(b);
  }
  document.body.append(m); menuAberto = m;
  const r = ancora.getBoundingClientRect(), h = m.offsetHeight;
  m.style.left = Math.max(8, Math.min(r.left, innerWidth - 184)) + "px";
  m.style.top = (r.bottom + h + 8 > innerHeight ? Math.max(8, r.top - h - 4) : r.bottom + 4) + "px";
  m.querySelector("button:not(.cur)")?.focus();
}
document.addEventListener("pointerdown", e => { if (menuAberto && !e.target.closest(".menu")) fecharMenu(); }, true);
document.addEventListener("keydown", e => { if (e.key === "Escape") fecharMenu(); });
const doId = ids => [].concat(ids).map(id => D.itens.find(i => i.id === id)).filter(Boolean);
const igual = (its, f) => new Set(its.map(f)).size === 1 ? f(its[0]) : null;  // "atual" só se todos estão iguais
function menuMover(a, ids, antes) {
  const its = doId(ids), atual = igual(its, pasta);
  popover(a, its.length > 1 ? `Mover ${its.length} itens para…` : "Mover para…",
    PASTAS.map(([p, n]) => ({ txt: n, atual: p === atual, fn: () => { antes?.(); editar(ids, "contexto", p); } })));
}
function menuNivel(a, ids, antes) {
  const its = doId(ids), atual = igual(its, i => nivel(i)[0]);
  popover(a, its.length > 1 ? `Criticidade de ${its.length} itens` : "Criticidade",
    NIVEIS.map(([v, n]) => ({ txt: n, atual: v === atual, fn: () => { antes?.(); editar(ids, "prioridade", v); } })));
}

// ---- seleção múltipla ----
const cardsVisiveis = () => [...document.querySelectorAll("#vista article.c[data-id]")];
function marcarSel() {
  for (const c of cardsVisiveis()) c.classList.toggle("sel", sel.has(+c.dataset.id));
  const b = $("barra"), n = sel.size;
  document.body.classList.toggle("com-barra", !!(n || modoSel));
  if (!n && !modoSel) { b.hidden = true; return; }
  const ids = [...sel], off = btn => { btn.disabled = !n; return btn; };
  b.replaceChildren(el("span", "n", n ? `${n} selecionado${n > 1 ? "s" : ""}` : "Toque nos cards para selecionar"),
    off(botao("", [ic("check"), "Feito"], "Marcar como feitos", () => lote("estado", "feito"))),
    off(botao("", [ic("move"), "Mover"], "Mover para…", e => menuMover(e.currentTarget, ids, limparSel))),
    off(botao("", [ic("alert"), "Criticidade"], "Mudar criticidade", e => menuNivel(e.currentTarget, ids, limparSel))),
    off(botao("tr", [ic("trash"), "Excluir"], "Excluir (vai para a Lixeira)", () => lote("estado", "arquivado"))),
    botao("x", [ic("x")], "Limpar seleção (Esc)", limparSel));
  b.hidden = false;
}
function limparSel() { sel.clear(); ancora = null; modoSel = false; marcarSel(); document.querySelector(".bsel")?.classList.remove("on"); }
function lote(campo, valor) { const ids = [...sel]; limparSel(); editar(ids, campo, valor); }
function clicarCard(e, id) {
  if (arrastou) { arrastou = false; return; }
  if (e.target.closest("button,.rs")) return;
  if (e.shiftKey && ancora != null) {  // intervalo na ordem em que os cards aparecem
    const ordem = cardsVisiveis().map(c => +c.dataset.id), a = ordem.indexOf(ancora), b = ordem.indexOf(id);
    if (!(e.ctrlKey || e.metaKey)) sel.clear();
    if (a < 0) { sel.add(id); ancora = id; } else ordem.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(x => sel.add(x));
  } else if (e.ctrlKey || e.metaKey || modoSel) {
    sel.has(id) ? sel.delete(id) : sel.add(id); ancora = id;
  } else if (e.pointerType === "mouse") {  // clique simples (como no Explorer): marca só este; de novo, desmarca
    if (sel.size === 1 && sel.has(id)) { sel.clear(); ancora = null; } else { sel = new Set([id]); ancora = id; }
  } else if (sel.size) { sel.clear(); ancora = null; }  // toque fora do modo Selecionar só limpa
  else return;
  marcarSel();
}

// ---- laço: segurar no espaço vazio e arrastar marca os cards que o retângulo tocar ----
// ponytail: sem rolagem automática na borda; laço maior que a tela, role antes ou use Shift+clique
document.addEventListener("pointerdown", ini => {
  if (ini.pointerType !== "mouse" || ini.button || $("app").hidden || dlgAberto) return;
  if (!ini.target.closest("main") || ini.target.closest("article,button,input,textarea,select,label,.menu,.cin")) return;
  if (!cardsVisiveis().length) return;
  ini.preventDefault();  // não seleciona texto da página
  const base = ini.ctrlKey || ini.metaKey || ini.shiftKey ? new Set(sel) : new Set();
  let laco = null;
  const mover = e => {
    if (!laco) {
      if (Math.hypot(e.clientX - ini.clientX, e.clientY - ini.clientY) < 5) return;
      laco = el("div", "laco"); document.body.append(laco); gesto = true; fecharMenu();
    }
    const x1 = Math.min(ini.clientX, e.clientX), x2 = Math.max(ini.clientX, e.clientX);
    const y1 = Math.min(ini.clientY, e.clientY), y2 = Math.max(ini.clientY, e.clientY);
    laco.style.cssText = `left:${x1}px;top:${y1}px;width:${x2 - x1}px;height:${y2 - y1}px`;
    sel = new Set(base);
    for (const c of cardsVisiveis()) {
      const r = c.getBoundingClientRect();
      if (r.left < x2 && r.right > x1 && r.top < y2 && r.bottom > y1) { sel.add(+c.dataset.id); ancora = +c.dataset.id; }
    }
    marcarSel();
  };
  const soltar = () => {
    document.removeEventListener("pointermove", mover); document.removeEventListener("pointerup", soltar);
    if (laco) { laco.remove(); gesto = false; }
    else if (!base.size && sel.size) limparSel();  // clique no vazio limpa a seleção
  };
  document.addEventListener("pointermove", mover); document.addEventListener("pointerup", soltar);
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && (sel.size || modoSel)) return limparSel();
  if (e.target.closest("input,textarea,select") || dlgAberto || $("app").hidden) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a" && cardsVisiveis().length) {
    e.preventDefault(); cardsVisiveis().forEach(c => sel.add(+c.dataset.id)); marcarSel();
  } else if (e.key === "Delete" && sel.size) lote("estado", "arquivado");  // reversível: vai para a Lixeira
});

// ---- tarefa criada à mão (sem IA) ----
function opcoes(s, lista, padrao) { for (const [v, t] of lista) { const o = el("option", "", t); o.value = v; s.append(o); } s.value = padrao; return s; }
function novaTarefa() {
  dlgAberto = true; fecharMenu();
  const v = el("div", "veu"), f = el("form", "dlg nova"), fim = () => { v.remove(); f.remove(); dlgAberto = false; };
  const campo = (rot, ctl) => { const l = el("label"); l.append(el("span", "", rot), ctl); return l; };
  const titulo = el("input"); titulo.required = true; titulo.maxLength = 200; titulo.placeholder = "O que precisa fazer?";
  const pastaS = opcoes(el("select"), PASTAS, NOME[vista] ? vista : "casa");
  const tipo = opcoes(el("select"), TIPOS.map(t => [t, t]), "tarefa");
  const crit = opcoes(el("select"), [["", "automática"], ...NIVEIS.map(([v, n]) => [v, n])], "");
  const prazo = el("input"); prazo.maxLength = 60; prazo.placeholder = "ex.: sexta 14h, amanhã, dia 20"; prazo.value = vista === "hoje" ? "hoje" : "";
  const erro = el("p", "erro"), pe = el("div"), no = el("button", "no", "Cancelar"), si = el("button", "si ok", "Criar");
  no.type = "button"; no.onclick = fim; v.onclick = fim;
  f.onkeydown = e => { if (e.key === "Escape") fim(); };
  f.onsubmit = async e => {
    e.preventDefault(); si.disabled = true;
    try {
      const r = await api("/api/itens", { titulo: titulo.value, contexto: pastaS.value, tipo: tipo.value, prioridade: crit.value || null, prazo: prazo.value || null });
      fim(); toast(r.descricao); ultimo = ""; atualizar();
    } catch (x) { si.disabled = false; erro.textContent = typeof x.detail === "string" ? x.detail : "Não consegui criar. O PC está ligado?"; }
  };
  const linha2 = el("div", "duas"); linha2.append(campo("Pasta", pastaS), campo("Tipo", tipo));
  const linha3 = el("div", "duas"); linha3.append(campo("Prazo", prazo), campo("Criticidade", crit));
  pe.append(no, si);
  f.append(el("h4", "", "Nova tarefa"), campo("Título", titulo), linha2, linha3, erro, pe);
  document.body.append(v, f); titulo.focus();
}
// ---- formulário genérico (nova pasta, apagar pasta) ----
const rotulado = (rot, ctl) => { const l = el("label"); l.append(el("span", "", rot), ctl); return l; };
function formulario(titulo, campos, rotulo, classe, enviar) {
  dlgAberto = true; fecharMenu();
  const v = el("div", "veu"), f = el("form", "dlg nova"), fim = () => { v.remove(); f.remove(); dlgAberto = false; };
  const erro = el("p", "erro"), pe = el("div"), no = el("button", "no", "Cancelar"), si = el("button", ("si " + classe).trim(), rotulo);
  no.type = "button"; no.onclick = fim; v.onclick = fim;
  f.onkeydown = e => { if (e.key === "Escape") fim(); };
  f.onsubmit = async e => {
    e.preventDefault(); si.disabled = true;
    try { const depois = await enviar(); fim(); depois?.(); }  // `depois` roda já sem o diálogo (atualizar redesenha)
    catch (x) { si.disabled = false; erro.textContent = typeof x.detail === "string" ? x.detail : "Não consegui salvar. O PC está ligado?"; }
  };
  pe.append(no, si); f.append(el("h4", "", titulo), ...campos, erro, pe);
  document.body.append(v, f); f.querySelector("input,select")?.focus();
}
function novaPasta() {
  const nome = el("input"); nome.required = true; nome.maxLength = 40; nome.placeholder = "ex.: Projetos pessoais";
  const desc = el("input"); desc.maxLength = 200; desc.placeholder = "ex.: site pessoal, side projects";
  formulario("Nova pasta", [rotulado("Nome", nome), rotulado("O que entra aqui (ajuda a IA a acertar)", desc)], "Criar", "ok", async () => {
    const r = await api("/api/pastas", { nome: nome.value, descricao: desc.value });
    return async () => { toast(`Pasta “${r.nome}” criada`); ultimo = ""; await atualizar(); ir(r.slug); };
  });
}
function apagarPasta(slug) {
  const n = D.itens.filter(i => pasta(i) === slug).length + D.lixeira.filter(i => i.contexto === slug).length;
  const destino = opcoes(el("select"), [...PASTAS.filter(([p]) => p !== slug), ["lixeira", "Lixeira (excluir os itens)"]], "outro");
  const campos = n ? [el("p", "", `${n} item(ns) desta pasta vão para:`), destino] : [el("p", "", "A pasta está vazia.")];
  formulario(`Apagar a pasta “${NOME[slug]}”?`, campos, "Apagar pasta", "", async () => {
    const r = await api(`/api/pastas/${encodeURIComponent(slug)}/apagar`, { destino: n ? destino.value : "outro" });
    (vistos ||= new Set()).add(r.grupo);  // sem aviso de Desfazer: a pasta já não existe para os itens voltarem
    return () => { toast(r.descricao); ir("hoje"); ultimo = ""; atualizar(); };
  });
}
const botaoNova = () => botao("bnova", [el("b", "", "+"), "Nova"], "Criar tarefa à mão", novaTarefa);
const botaoSel = () => botao("bsel" + (modoSel ? " on" : ""), ["Selecionar"], "Selecionar vários (no PC: Ctrl+clique, Shift+clique, Ctrl+A)",
  e => { modoSel = !modoSel; if (!modoSel) sel.clear(); e.currentTarget.classList.toggle("on", modoSel); marcarSel(); });

function confirmar(titulo, texto, rotulo, fn) {
  dlgAberto = true;
  const v = el("div", "veu"), d = el("div", "dlg"), fim = () => { v.remove(); d.remove(); dlgAberto = false; };
  const pe = el("div");
  const no = el("button", "no", "Cancelar"), si = el("button", "si", rotulo);
  no.onclick = fim; v.onclick = fim;
  d.onkeydown = e => { if (e.key === "Escape") fim(); };
  si.onclick = async () => { fim(); try { await fn(); } catch { toast("Não consegui apagar. O PC está ligado?"); } ultimo = ""; atualizar(); };
  pe.append(no, si); d.append(el("h4", "", titulo), el("p", "", texto), pe);
  document.body.append(v, d); no.focus();
}

// ---- arrastar: mouse na hora; toque depois de segurar ----
document.addEventListener("touchmove", e => { if (gesto) e.preventDefault(); }, { passive: false });
function arrastavel(card, it) {
  card.addEventListener("contextmenu", e => { if (matchMedia("(hover:none)").matches) e.preventDefault(); });
  card.addEventListener("pointerdown", ini => {
    if (ini.button || ini.target.closest("button,.rs")) return;
    const toque = ini.pointerType === "touch", r = card.getBoundingClientRect();
    const grabX = ini.clientX - r.left, grabY = ini.clientY - r.top;
    let clone = null, alvo = null, ph = null, cel = null, timer = null;
    const grid = matchMedia(AREA_GRADE).matches && gradeAtual ? card.closest(".grid") : null, t = tam(it);

    const marcar = novo => { if (alvo !== novo) { alvo?.classList.remove("over"); novo?.classList.add("over"); alvo = novo; } };
    const comecar = () => {
      gesto = true; fecharMenu();
      clone = card.cloneNode(true); clone.classList.add("drag");
      if (sel.has(it.id) && sel.size > 1) clone.append(el("span", "qtd", String(sel.size)));
      clone.style.cssText = `width:${r.width}px;height:${r.height}px;left:${r.left}px;top:${r.top}px;margin:0`;
      document.body.append(clone); card.classList.add("saiu");
      document.body.style.cursor = "grabbing";
      if (navigator.vibrate && toque) navigator.vibrate(15);
    };
    const mover = e => {
      if (!clone) {
        const dist = Math.hypot(e.clientX - ini.clientX, e.clientY - ini.clientY);
        if (toque) { if (dist > 10) limpar(); return; }  // mexeu antes de segurar: é rolagem
        if (dist < 5) return;
        comecar();
      }
      clone.style.left = e.clientX - grabX + "px"; clone.style.top = e.clientY - grabY + "px";
      const sob = document.elementFromPoint(e.clientX, e.clientY);
      marcar(sob?.closest("[data-alvo]") || null);
      cel = null; ph?.remove(); ph = null;
      if (!alvo && grid) {
        const g = grid.getBoundingClientRect(), largCel = (g.width - GAP * (COLS - 1)) / COLS;
        if (e.clientX >= g.left - 40 && e.clientX <= g.right + 40) {
          const col = Math.min(COLS - t.larg + 1, Math.max(1, Math.round((e.clientX - grabX - g.left) / (largCel + GAP)) + 1));
          const lin = Math.max(1, Math.round((e.clientY - grabY - g.top) / (ALT_LIN + GAP)) + 1);
          cel = { id: it.id, col, lin, larg: t.larg, alt: t.alt };
          ph = el("div", "ph"); ph.style.gridColumn = `${col}/span ${t.larg}`; ph.style.gridRow = `${lin}/span ${t.alt}`;
          grid.append(ph);
        }
      }
    };
    const limpar = () => {
      clearTimeout(timer);
      document.removeEventListener("pointermove", mover); document.removeEventListener("pointerup", soltar); document.removeEventListener("pointercancel", cancelar);
      clone?.remove(); ph?.remove(); alvo?.classList.remove("over"); card.classList.remove("saiu");
      document.body.style.cursor = "";
      gesto = false;
    };
    const cancelar = () => limpar();
    const soltar = () => {
      const a = alvo?.dataset.alvo, c = cel, ativo = !!clone;
      limpar();
      if (!ativo) return;
      arrastou = true; setTimeout(() => { arrastou = false; }, 0);  // o clique que vem depois do soltar não seleciona
      const ids = sel.has(it.id) && sel.size > 1 ? [...sel] : [it.id];
      if (ids.length > 1 && a) limparSel();
      if (a === "lixeira") editar(ids, "estado", "arquivado");
      else if (a && (ids.length > 1 || a !== pasta(it))) editar(ids, "contexto", a);
      else if (c) fixarGrade(c);
    };
    document.addEventListener("pointermove", mover); document.addEventListener("pointerup", soltar); document.addEventListener("pointercancel", cancelar);
    if (toque) timer = setTimeout(comecar, 300);
  });
}
function redimensionavel(alca, card, it, p) {
  alca.addEventListener("pointerdown", ini => {
    ini.stopPropagation(); ini.preventDefault();
    gesto = true; fecharMenu();
    const grade = card.closest(".grid"), r = card.getBoundingClientRect(), g = grade.getBoundingClientRect(), largCel = (g.width - GAP * (COLS - 1)) / COLS;
    const cards = new Map(cardsVisiveis().map(c => [+c.dataset.id, c]));
    const etiqueta = el("span", "tamanho");
    let larg = p.larg, alt = p.alt;
    // prévia: o card já assume o tamanho e os outros já vão para onde vão ficar ao soltar
    const previa = () => {
      const pos = arranjar(gradeAtual, { id: it.id, col: p.col, lin: p.lin, larg, alt });
      let fundo = 0;
      for (const [id, q] of pos) {
        const c = cards.get(id);
        if (c) { c.style.gridColumn = `${q.col}/span ${q.larg}`; c.style.gridRow = `${q.lin}/span ${q.alt}`; }
        fundo = Math.max(fundo, q.lin + q.alt);
      }
      grade.style.minHeight = (fundo + 2) * (ALT_LIN + GAP) + "px";  // espaço para crescer para baixo
      etiqueta.textContent = `${larg} × ${alt}`;
    };
    card.classList.add("rsz"); grade.classList.add("guias"); card.append(etiqueta);
    document.body.style.cursor = "nwse-resize";
    previa();
    const mover = e => {
      const l = Math.min(COLS - p.col + 1, Math.max(1, Math.round((e.clientX - r.left + GAP) / (largCel + GAP))));
      const a = Math.min(4, Math.max(1, Math.round((e.clientY - r.top + GAP) / (ALT_LIN + GAP))));
      if (l !== larg || a !== alt) { larg = l; alt = a; previa(); }
    };
    const soltar = () => {
      document.removeEventListener("pointermove", mover); document.removeEventListener("pointerup", soltar);
      etiqueta.remove(); card.classList.remove("rsz"); grade.classList.remove("guias"); grade.style.minHeight = "";
      document.body.style.cursor = "";
      gesto = false;
      if (larg !== p.larg || alt !== p.alt) fixarGrade({ id: it.id, col: p.col, lin: p.lin, larg, alt });
      else { ultimo = ""; render(); }
    };
    document.addEventListener("pointermove", mover); document.addEventListener("pointerup", soltar);
  });
}

// ---- desenho ----
function cartao(it, comPasta) {
  const a = el("article", `c ${nivel(it)[0]} ${it.estado}${sel.has(it.id) ? " sel" : ""}`);
  a.dataset.id = it.id;
  a.addEventListener("click", e => clicarCard(e, it.id));
  const k = el("span", "k"); k.append(ic(document.getElementById(it.tipo) ? it.tipo : "nota"), it.tipo || "nota");
  if (comPasta) k.append(el("em", "", NOME[pasta(it)] || pasta(it)));
  const barras = el("i");
  for (let n = 1; n <= 4; n++) barras.append(el("u", n <= nivel(it)[2] ? "on" : ""));
  const sig = botao("sig", [nivel(it)[1], barras], "Mudar criticidade", e => menuNivel(e.currentTarget, it.id));
  const meta = el("div", "meta"); meta.append(k, sig);
  const h = el("h3", "", it.titulo); h.title = it.titulo || "";
  a.append(meta, h);
  if (atrasado(it)) {
    const n = -dias(it.prazo_em), chip = el("span", "chip"), d = el("div", "due");
    chip.append(ic("alert"), `atrasado ${n} dia${n > 1 ? "s" : ""}`); d.append(chip); a.append(d);
  } else if (it.prazo_em) {
    const d = el("div", "due"); d.append(ic("clock"), txtPrazo(it.prazo_em)); a.append(d);
  }
  const acts = el("div", "acts"), dir = el("div");
  const feito = aberto(it);
  dir.append(botao("mv", [ic("move")], "Mover para…", e => menuMover(e.currentTarget, it.id)),
    botao("tr", [ic("trash")], "Excluir", () => editar(it.id, "estado", "arquivado")));
  acts.append(botao("ok", [ic(feito ? "check" : "retry")], feito ? "Marcar como feito" : "Reabrir", () => editar(it.id, "estado", feito ? "feito" : "catalogado")), dir);
  a.append(acts);
  arrastavel(a, it);
  return a;
}
function cabecalho(titulo, sub, ...ctl) {
  const h = el("div", "hd"); h.append(el("h2", "", titulo), el("span", "", sub));
  if (ctl.length) { const c = el("div", "ctl"); c.append(...ctl); h.append(c); }
  return h;
}
function chaveFeitos(n) {
  return botao("tg" + (verFeitos ? " on" : ""), [el("i"), `Mostrar feitos (${n})`], null, () => { verFeitos = !verFeitos; render(); });
}
function vHoje(v) {
  const base = D.itens.filter(i => i.prazo_em && dias(i.prazo_em) <= 0);
  const atras = base.filter(atrasado), hoje = base.filter(i => dias(i.prazo_em) === 0);
  const abertosHoje = hoje.filter(aberto), feitos = hoje.length - abertosHoje.length;
  const n = atras.length + abertosHoje.length, ps = new Set([...atras, ...abertosHoje].map(pasta)).size;
  const d = new Date();
  v.append(cabecalho("Hoje", `${n} aberto${n === 1 ? "" : "s"} em ${ps} pasta${ps === 1 ? "" : "s"} · ${SEMANA[d.getDay()]}, ${d.getDate()}/${d.getMonth() + 1}`, botaoNova(), botaoSel(), chaveFeitos(feitos)));
  const secao = (t, l) => {
    if (!l.length) return;
    v.append(el("div", "sec", `${t} · ${l.length}`));
    const g = el("div", "grid");
    for (const i of [...l].sort(urgencia)) {
      const c = cartao(i, true), s = tam(i);
      c.style.gridColumn = `span ${s.larg}`;
      if (s.larg > 1) c.classList.add("w2");
      c.style.setProperty("--l", s.larg > 1 ? 1 : 2);
      g.append(c);
    }
    v.append(g);
  };
  secao("ATRASADOS", atras); secao("HOJE", verFeitos ? hoje : abertosHoje);
  if (!n && !feitos) v.append(el("p", "vazio", "Nada para hoje."));
}
function vPasta(v) {
  const todos = D.itens.filter(i => pasta(i) === vista), abertos = todos.filter(aberto);
  const crit = abertos.filter(i => nivel(i)[0] === "critica").length, altas = abertos.filter(i => nivel(i)[0] === "alta").length;
  const lista = (verFeitos ? todos : abertos).filter(i => !filtro || nivel(i)[0] === filtro);
  const ft = el("div", "ft");
  ft.append(botao(filtro ? "" : "on", ["Todas"], null, () => { filtro = null; render(); }));
  for (const [val, n] of NIVEIS) ft.append(botao(filtro === val ? "on" : "", [n], null, () => { filtro = val; render(); }));
  v.append(cabecalho(NOME[vista], `${abertos.length} aberto${abertos.length === 1 ? "" : "s"}${crit ? ` · ${crit} crítica${crit === 1 ? "" : "s"}` : ""} · ${altas} alta${altas === 1 ? "" : "s"}`, botaoNova(), botaoSel(), ft, chaveFeitos(todos.length - abertos.length),
    ...(vista === "outro" ? [] : [botao("perigo", ["Apagar pasta"], "Apagar esta pasta (os itens vão para outra)", () => apagarPasta(vista))])));
  if (!lista.length) { v.append(el("p", "vazio", filtro ? "Nada com essa criticidade." : "Pasta vazia.")); gradeAtual = null; return; }
  gradeAtual = lista;
  const pos = arranjar(lista), g = el("div", "grid");
  const emOrdem = [...lista].sort((a, b) => pos.get(a.id).lin - pos.get(b.id).lin || pos.get(a.id).col - pos.get(b.id).col);
  for (const i of emOrdem) {
    const p = pos.get(i.id), c = cartao(i);
    c.style.gridColumn = `${p.col}/span ${p.larg}`; c.style.gridRow = `${p.lin}/span ${p.alt}`;
    if (p.larg > 1) c.classList.add("w2");
    c.style.setProperty("--l", p.alt === 1 ? (p.larg > 1 ? 1 : 2) : p.alt * (p.larg > 1 ? 3 : 5));
    const alca = el("div", "rs"); alca.title = "Puxe para mudar o tamanho";
    redimensionavel(alca, c, i, p);
    c.append(alca); g.append(c);
  }
  v.append(g);
}
function vRevisar(v) {
  const l = D.revisar.filter(c => c.status === "falhou");
  v.append(cabecalho("Revisar", `${l.length} nota${l.length === 1 ? "" : "s"} que a IA não entendeu`));
  if (!l.length) return v.append(el("p", "vazio", "Nada para revisar."));
  const g = el("div", "lista");
  for (const c of l) {
    const a = el("article", "lx"), b = el("div", "bts"), acao = async (rota) => { try { await api(`/api/capturas/${c.id}/${rota}`, {}); } catch {} ultimo = ""; atualizar(); };
    b.append(botao("", [ic("retry"), "Tentar de novo"], null, () => acao("reprocessar")));
    if ((c.erro || "").startsWith("instrução não aplicada")) b.append(botao("", ["Guardar como anotação"], null, () => acao("como-nota")));
    const h = el("h3", "", c.texto);
    if (c.erro) h.title = c.erro;
    a.append(h, b); g.append(a);
  }
  v.append(g);
}
function vLixeira(v) {
  const l = D.lixeira, esv = botao("perigo", ["Esvaziar"], null, () => confirmar("Esvaziar a Lixeira?", `${l.length} item(ns) somem para sempre. Isso não tem Desfazer.`, "Apagar de vez", () => api("/api/lixeira/esvaziar", {})));
  v.append(l.length ? cabecalho("Lixeira", `${l.length} ite${l.length === 1 ? "m" : "ns"}`, esv) : cabecalho("Lixeira", "0 itens"));
  if (!l.length) return v.append(el("p", "vazio", "Lixeira vazia."));
  const g = el("div", "lista");
  for (const it of l) {
    const a = el("article", "lx"), m = el("div", "meta"), k = el("span", "k"), b = el("div", "bts");
    k.append(ic("trash"), `de ${NOME[pasta(it)] || pasta(it)}`); m.append(k);
    b.append(botao("", [ic("undo"), "Restaurar"], null, () => editar(it.id, "estado", "catalogado")),
      botao("del", [ic("trash"), "Apagar de vez"], null, () => confirmar("Apagar de vez?", `“${it.titulo}” some para sempre. Isso não tem Desfazer.`, "Apagar de vez", () => api(`/api/itens/${it.id}/apagar`, {}))));
    a.append(m, el("h3", "", it.titulo), b); g.append(a);
  }
  v.append(g);
}
function ir(v) { vista = v; filtro = null; sel.clear(); ancora = null; modoSel = false; try { localStorage.setItem(VISTA, v); } catch {} render(); scrollTo(0, 0); }
function desenhaNav() {
  const abertos = D.itens.filter(aberto), base = abertos.filter(i => i.prazo_em && dias(i.prazo_em) <= 0), atras = base.filter(atrasado).length;
  const linha = (id, conteudo, n, alvo) => {
    const b = botao("fold" + (vista === id ? " on" : ""), [], null, () => ir(id));
    const nm = el("span", "nm"); nm.append(...conteudo); b.append(nm, el("b", "", n));
    if (alvo) b.dataset.alvo = id;
    return b;
  };
  const logo = el("div", "logo"), longo = el("span", "longo"), curto = el("span", "curto");
  longo.append("dump", el("u", "", "box"), "_"); curto.append("d", el("u", "", "b"), "_"); logo.append(longo, curto);
  const hoje = [ic("sun"), "Hoje"];
  if (atras) hoje.push(el("span", "chip", `${atras} atrasado${atras > 1 ? "s" : ""}`));
  const lb = el("div", "lb"); lb.append(el("span", "", "PASTAS"), el("span", "", "abertos"));
  const fim = el("div", "fim");
  fim.append(linha("revisar", [ic("alert"), "Revisar"], D.revisar.filter(c => c.status === "falhou").length),
    linha("lixeira", [ic("trash"), "Lixeira"], D.lixeira.length, true),
    botao("sair", ["sair"], null, async () => { await api("/api/logout", {}); mostra("login"); }));
  $("nav").replaceChildren(logo, linha("hoje", hoje, base.length), lb,
    ...PASTAS.map(([p, n]) => linha(p, [n], abertos.filter(i => pasta(i) === p).length, true)),
    botao("fold mais", [el("span", "nm", "+"), el("span", "rot", "Nova pasta")], "Criar pasta", novaPasta), fim);
}
function render() {
  gradeAtual = null;
  desenhaNav();
  const v = $("vista"); v.replaceChildren();
  if (vista === "hoje") vHoje(v);
  else if (vista === "revisar") vRevisar(v);
  else if (vista === "lixeira") vLixeira(v);
  else if (NOME[vista]) vPasta(v);
  else return ir("hoje");
  const naTela = new Set(cardsVisiveis().map(c => +c.dataset.id));
  for (const id of sel) if (!naTela.has(id)) sel.delete(id);
  marcarSel();
}
function avisos(alts) {
  if (!vistos) { vistos = new Set(alts.map(a => a.grupo)); return; }
  for (const a of alts) if (!vistos.has(a.grupo)) {  // instrução digitada na caixa, aplicada pelo worker
    vistos.add(a.grupo);
    if (!a.desfeito) toast(a.descricoes.slice(0, 2).join(" · ") + (a.descricoes.length > 2 ? ` · e mais ${a.descricoes.length - 2}` : ""), a.grupo);
  }
}
async function atualizar() {
  try {
    const [r, alts] = await Promise.all([api("/api/itens"), api("/api/alteracoes")]);
    avisos(alts);
    const s = JSON.stringify(r);
    if (gesto || menuAberto || dlgAberto) return;  // não redesenha no meio de um arraste ou menu
    if (s !== ultimo) {
      ultimo = s; D = r;
      if (r.pastas?.length) { PASTAS = r.pastas.map(p => [p.slug, p.nome]); NOME = Object.fromEntries(PASTAS); }
      render();
    }
    mostrarFila();
  } catch {}
}

// ---- captura ----
const crescer = () => { const t = $("txt"); t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; };
$("txt").addEventListener("input", crescer);
$("txt").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $("guardar").click(); } });
$("guardar").onclick = async () => {
  const texto = $("txt").value.trim(); if (!texto) return;
  const f = lerFila(); f.push({ id: uuid(), texto }); gravaFila(f);
  $("txt").value = ""; crescer(); await enviarFila(); atualizar();
};

// ---- login ----
$("entrar").onclick = async () => {
  try { await api("/api/login", { senha: $("senha").value }); $("senha").value = ""; $("err").textContent = ""; iniciar(); }
  catch { $("err").textContent = "senha incorreta ou muitas tentativas"; }
};
$("senha").addEventListener("keydown", e => { if (e.key === "Enter") $("entrar").click(); });
$("criar").onclick = async () => {
  const a = $("nsenha").value, b = $("nsenha2").value;
  if (a !== b) { $("serr").textContent = "As senhas não conferem."; return; }
  try { await api("/api/setup", { senha: a }); $("nsenha").value = $("nsenha2").value = ""; iniciar(); }
  catch (e) {
    const s = String(e.message);
    $("serr").textContent =
      s === "403" ? "Crie a senha abrindo o app no próprio PC (http://127.0.0.1:8000), não por link externo." :
      s === "409" ? "A senha já foi criada. Recarregue a página e entre." :
      s === "422" ? "Use pelo menos 8 caracteres." :
      /^\d+$/.test(s) ? `Erro ${s} no servidor${typeof e.detail === "string" ? ": " + e.detail : ""}.` :
      "Não consegui falar com o servidor. O dumpbox está aberto? Confira o endereço da página.";
  }
};
async function iniciar() {
  const e = await estado();
  if (e && !e.configurado) return mostra("setup");
  // 401 -> api() já mostrou o login; offline -> segue no app (a fila local guarda as notas)
  try { await api("/api/sessao"); } catch (e) { if (String(e.message) === "401") return; }
  mostra("app"); await enviarFila(); atualizar();
}
window.addEventListener("online", () => { enviarFila().then(atualizar); });
setInterval(() => { if (!$("app").hidden) { enviarFila(); atualizar(); } }, 5000);
setInterval(() => { if (!$("prep").hidden) estado(); }, 3000);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
iniciar();

// ---- janela flutuante da IA: executa na hora, com Desfazer ----
const hist = [];
function abrirIA(sim) {
  $("ia").hidden = !sim; $("iamini").hidden = true;
  $("fab").replaceChildren(ic(sim ? "x" : "chat"));
  if (sim) $("cmsg").focus();
}
$("fab").onclick = () => abrirIA($("ia").hidden);
$("ia-x").onclick = () => abrirIA(false);
function desfazerIA(grupo, depois) {
  return async () => { try { await api("/api/desfazer", { grupo }); depois(); } catch {} ultimo = ""; atualizar(); };
}
async function enviarChat() {
  const m = $("cmsg").value.trim(); if (!m) return;
  $("cmsg").value = "";
  const msgs = $("msgs"), esp = el("div", "rsp", "…");
  msgs.append(el("div", "msg", m), esp); esp.scrollIntoView({ block: "end" });
  try {
    const r = await api("/api/chat", { mensagem: m, historico: hist.slice(-6) });
    hist.push({ role: "user", content: m }, { role: "assistant", content: r.resposta });
    esp.textContent = r.resposta;
    if (r.feitas.length) {
      const lista = el("div", "res");
      for (const f of r.feitas) { const p = el("p"); p.append(ic("check"), el("span", "", f)); lista.append(p); }
      msgs.append(lista);
    }
    if (r.grupo) {
      (vistos ||= new Set()).add(r.grupo);
      const u = el("button", "undo"); u.append(ic("undo"), "Desfazer");
      u.onclick = desfazerIA(r.grupo, () => u.replaceChildren("Desfeito"));
      msgs.append(u);
      if (!matchMedia(AREA_GRADE).matches) {  // na tela pequena a janela cobre os cards: encolhe para uma linha
        const mini = $("iamini"), s = el("span", "", `${r.feitas.length} feita${r.feitas.length > 1 ? "s" : ""}`);
        const d = el("button", "", "Desfazer");
        s.onclick = () => abrirIA(true);
        d.onclick = desfazerIA(r.grupo, () => { mini.hidden = true; });
        mini.replaceChildren(ic("check"), s, d);
        $("ia").hidden = true; mini.hidden = false; $("fab").replaceChildren(ic("chat"));
      }
    }
    msgs.lastElementChild.scrollIntoView({ block: "end" });
    ultimo = ""; atualizar();
  } catch (e) {
    const s = String(e.message);
    esp.textContent = s === "503" ? "Modelo indisponível: a IA ainda está sendo preparada ou o Ollama está desligado no PC." :
      /^\d+$/.test(s) ? `Erro ${s} no servidor.` : "Sem conexão com o servidor. O dumpbox.exe está aberto no PC?";
  }
}
$("cenviar").onclick = enviarChat;
$("cmsg").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarChat(); } });
