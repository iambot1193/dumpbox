// PWA: fila local de capturas (localStorage) -> envia ao servidor quando houver conexão.
// Todo texto vindo do servidor entra via textContent (nunca innerHTML).
const $ = id => document.getElementById(id);
const FILA = "dumpbox.fila", VISTA = "dumpbox.vista";
const lerFila = () => { try { return JSON.parse(localStorage.getItem(FILA) || "[]"); } catch { return []; } };
const gravaFila = f => { try { localStorage.setItem(FILA, JSON.stringify(f)); return true; } catch { return false; } };
const horaLocal = (d = new Date()) => new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 19);  // hora local sem fuso, como o servidor
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
let sel = new Set(), ancora = null, modoSel = false, arrastou = false, semClique = 0;  // seleção múltipla (Ctrl/Shift ou modo Selecionar)
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
  let r;
  try {
    r = await fetch(url, { method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (e) {  // sem rede (TypeError): edições vão para a fila do aparelho; o resto espera o PC
    const o = body !== undefined && e instanceof TypeError && offline(url, body);
    if (o) return o;
    throw e;
  }
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
    if (!p.pronto) b.textContent = e.aviso ? e.aviso : p.erro ? `Erro ao preparar a IA: ${p.erro}` : `Preparando a IA (só na primeira vez): ${p.msg || "aguarde"} ${p.pct ? p.pct + "%" : ""}`;
    return e;
  } catch {
    const b = $("prep"); b.hidden = false; topo();
    b.textContent = "Sem conexão com o servidor. O dumpbox.exe está aberto no PC? Suas notas ficam na fila e são enviadas quando ele voltar.";
    return null;
  }
}

// ---- sem o PC (docs/plano-sync.md): cópia da última lista + fila de alterações; ao voltar, POST /api/sync ----
// ponytail: localStorage (~5 MB, sobra para milhares de cards); IndexedDB se um dia faltar espaço
const COPIA = "dumpbox.copia", ALT = "dumpbox.alteracoes";
const lerAlt = () => { try { return JSON.parse(localStorage.getItem(ALT) || "[]"); } catch { return []; } };
const gravaAlt = a => { try { localStorage.setItem(ALT, JSON.stringify(a)); } catch {} };
const guardaCopia = () => { try { localStorage.setItem(COPIA, JSON.stringify(D)); } catch {} };
function aplicaLocal(a) {
  const i = D.itens.find(x => x.id === a.item_id);
  if (!i) return;
  if (a.campo === "grade") { const p = JSON.parse(a.valor); Object.assign(i, { grade_col: p.col, grade_lin: p.lin, grade_larg: p.larg, grade_alt: p.alt }); }
  else if (a.campo === "prazo") { if (a.valor === "limpar") i.prazo_em = null; else if (/^\d{4}-/.test(a.valor)) i.prazo_em = a.valor; }  // "amanhã": o PC resolve
  else i[a.campo] = a.valor || null;
  if (a.campo === "estado" && a.valor === "arquivado") {
    D.itens = D.itens.filter(x => x !== i);
    D.lixeira.unshift({ id: i.id, titulo: i.titulo, contexto: i.contexto, tipo: i.tipo });
  }
}
function offline(url, body) {  // devolve a resposta "de mentira" ou null (rota que só o PC faz: criar pasta, chat, apagar de vez...)
  const m = url.match(/^\/api\/itens\/(\d+)\/editar$/), quando = horaLocal(), novas = [];
  const add = (item_id, campo, valor) => novas.push({ id: uuid(), item_id, campo, valor, quando });
  if (url === "/api/itens/editar") body.ids.forEach(i => add(i, body.campo, body.valor));
  else if (m) for (const [k, v] of Object.entries(body.mudancas)) add(+m[1], k, v);
  else if (url === "/api/layout") body.itens.forEach(p => add(p.id, "grade", JSON.stringify(p)));
  else return null;
  gravaAlt([...lerAlt(), ...novas]);
  novas.forEach(aplicaLocal); guardaCopia(); mostrarFila();
  if (url !== "/api/layout") toast("Sem o PC: guardado neste aparelho, vai quando ele voltar");
  return { grupo: null, descricao: null, n: novas.length, ok: true };
}

function mostrarFila() {
  const q = lerFila().length, a = lerAlt().length, p = D.revisar.filter(c => c.status === "pendente").length, partes = [];
  if (p) partes.push(`processando ${p} nota${p > 1 ? "s" : ""}`);
  if (q) partes.push(`${q} na fila, aguardando o PC`);
  if (a) partes.push(`${a} alteraç${a > 1 ? "ões" : "ão"} aguardando o PC`);
  $("st").replaceChildren(...(partes.length ? [ic("spin"), partes.join(" · ")] : []));
}
async function enviarFila() {
  let fila = lerFila();
  for (const n of [...fila]) {
    try { await api(n.imagem ? "/api/capturas/imagem" : "/api/capturas", n); fila = fila.filter(x => x.id !== n.id); gravaFila(fila); }
    catch (e) { if (String(e.message) === "401") return; break; }
  }
  const alts = lerAlt();
  if (alts.length) {
    try { await api("/api/sync", { agora_cliente: horaLocal(), alteracoes: alts }); }
    catch (e) { if (String(e.message) !== "422") return mostrarFila(); toast("O PC recusou alterações feitas sem ele."); }  // 422: nunca vai passar, não trava a fila
    const ids = new Set(alts.map(a => a.id));
    gravaAlt(lerAlt().filter(a => !ids.has(a.id))); ultimo = "";
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
const REPETE = { diario: "todo dia", semanal: "toda semana", mensal: "todo mês" };
const LEMBRETES = [["", "sem lembrete"], ["0", "na hora do prazo"], ["15", "15 min antes"], ["30", "30 min antes"], ["60", "1 h antes"], ["1440", "1 dia antes"]];
const norm = s => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
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
    if (r.grupo) { (vistos ||= new Set()).add(r.grupo); toast(r.descricao, r.grupo, campo === "estado" && valor === "feito" ? "concluir" : null); }
    if (campo === "estado" && valor === "feito") sinal("feito");
    ultimo = ""; await atualizar();
  } catch (e) { if (String(e.message) !== "401") toast("Não consegui salvar. O PC está ligado?"); }
}
// ---- avisos (toast): preferências deste aparelho ----
// ponytail: localStorage por aparelho; ir para o servidor se quiser a mesma config em todos
const CFG_PADRAO = { mudo: false, concluir: true, mudancas: true, tempo: 9, puxar: true, som: true, diario: "" };
let CFG = { ...CFG_PADRAO };
try { Object.assign(CFG, JSON.parse(localStorage.getItem("dumpbox.avisos") || "{}")); } catch {}
const gravaCfg = () => { try { localStorage.setItem("dumpbox.avisos", JSON.stringify(CFG)); } catch {} };
let timerToast;
// tipo: "concluir" (marcou feito) ou "mudanca" (feita pela IA / outro aparelho). Silenciar só cala aviso de mudança
// (os que têm Desfazer); erro e resposta direta (copiado, colado...) sempre aparecem.
function toast(txt, grupo, tipo) {
  if (grupo && (CFG.mudo || (tipo === "concluir" && !CFG.concluir) || (tipo === "mudanca" && !CFG.mudancas))) return;
  const t = $("toast");
  t.replaceChildren(ic("check"), el("span", "", txt));
  if (grupo) t.append(botao("", [ic("undo"), "Desfazer"], null, async () => { t.hidden = true; await api("/api/desfazer", { grupo }); ultimo = ""; atualizar(); }));
  t.classList.toggle("puxa", CFG.puxar); t.style.transform = t.style.opacity = "";
  t.hidden = false;
  clearTimeout(timerToast); timerToast = setTimeout(() => { t.hidden = true; }, CFG.tempo * 1000);
}
// puxar o aviso para o lado fecha; toque parado passa para o que está embaixo (o aviso não bloqueia a tela)
$("toast").addEventListener("pointerdown", ini => {
  const t = $("toast");
  if (!CFG.puxar || ini.target.closest("button")) return;
  let dx = 0;
  const mover = e => { dx = e.clientX - ini.clientX; t.style.transform = `translateX(${dx}px)`; t.style.opacity = Math.max(.2, 1 - Math.abs(dx) / 200); };
  const soltar = e => {
    document.removeEventListener("pointermove", mover); document.removeEventListener("pointerup", soltar); document.removeEventListener("pointercancel", soltar);
    if (Math.abs(dx) > 60) { clearTimeout(timerToast); t.hidden = true; return; }
    t.style.transform = t.style.opacity = "";
    if (e.type === "pointerup" && Math.abs(dx) < 8) {  // toque: repassa o clique
      t.style.visibility = "hidden"; const sob = document.elementFromPoint(e.clientX, e.clientY); t.style.visibility = "";
      sob?.click();
    }
  };
  document.addEventListener("pointermove", mover); document.addEventListener("pointerup", soltar); document.addEventListener("pointercancel", soltar);
});
function menuAvisos(a) {
  const sim = v => v ? "sim" : "não", troca = k => () => { CFG[k] = !CFG[k]; gravaCfg(); menuAvisos(a); };
  const tempos = [4, 9, 20];
  popover(a, "Avisos", [
    { txt: `Silenciar avisos: ${sim(CFG.mudo)}`, fn: troca("mudo") },
    { txt: `Ao concluir: ${sim(CFG.concluir)}`, fn: troca("concluir") },
    { txt: `Mudanças da IA: ${sim(CFG.mudancas)}`, fn: troca("mudancas") },
    { txt: `Na tela: ${CFG.tempo} s`, fn: () => { CFG.tempo = tempos[(tempos.indexOf(CFG.tempo) + 1) % tempos.length]; gravaCfg(); menuAvisos(a); } },
    { txt: `Puxar p/ fechar: ${sim(CFG.puxar)}`, fn: troca("puxar") },
    { txt: `Som nos lembretes: ${sim(CFG.som)}`, fn: troca("som") },
    { txt: `Lembrete diário: ${CFG.diario || "desligado"}`, fn: () => {
      const hs = ["", "07:00", "08:00", "09:00", "12:00", "18:00", "21:00"];
      CFG.diario = hs[(hs.indexOf(CFG.diario) + 1) % hs.length]; gravaCfg();
      if (CFG.diario && temAvisos && Notification.permission === "default") Notification.requestPermission();
      menuAvisos(a);
    } },
    { txt: "Testar aviso", fn: () => { bipe(); toast("Assim aparece um aviso. Puxe para o lado para fechar."); } },
  ]);
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
  document.querySelector(".bsel")?.classList.toggle("on", modoSel);
  if (!n && !modoSel) { b.hidden = true; return; }
  const ids = [...sel], off = btn => { btn.disabled = !n; return btn; };
  b.replaceChildren(el("span", "n", n ? `${n} selecionado${n > 1 ? "s" : ""}` : "Toque nos cards para selecionar"),
    off(botao("", [ic("check"), "Feito"], "Marcar como feitos", () => lote("estado", "feito"))),
    off(botao("", [ic("copy"), "Copiar"], "Copiar os cards como texto (Ctrl+C)", () => copiar(ids))),
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
  if (performance.now() < semClique) return;  // clique que o celular solta depois de segurar o dedo
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

// ---- pincel: Shift + segurar o botão sobre um card e passar o mouse marca cada card por onde passar ----
// Soma à seleção atual. Shift+clique sem mexer continua sendo intervalo (clicarCard).
function pincel(ini, id) {
  ini.preventDefault();
  let ativo = false;
  const marca = !sel.has(id);  // card inicial já marcado: o gesto inteiro desmarca
  const add = n => {
    if (sel.has(n) === marca) return;
    if (marca) { sel.add(n); ancora = n; } else sel.delete(n);
    marcarSel();
  };
  const mover = e => {
    if (!ativo) {
      if (Math.hypot(e.clientX - ini.clientX, e.clientY - ini.clientY) < 5) return;
      ativo = gesto = true; fecharMenu(); add(id);
    }
    const c = document.elementFromPoint(e.clientX, e.clientY)?.closest("#vista article.c[data-id]");
    if (c) add(+c.dataset.id);
  };
  const soltar = () => {
    document.removeEventListener("pointermove", mover); document.removeEventListener("pointerup", soltar);
    if (!ativo) return;
    gesto = false;
    arrastou = true; setTimeout(() => { arrastou = false; }, 0);  // o clique depois do soltar não refaz como intervalo
  };
  document.addEventListener("pointermove", mover); document.addEventListener("pointerup", soltar);
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
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && sel.size && !String(getSelection())) { e.preventDefault(); copiar([...sel]); }
});

// ---- copiar e colar cards: texto de lista (Markdown) legível em qualquer lugar e que volta a virar card ----
// - [ ] Título (Freelance · tarefa · baixa · prazo 2026-11-20 14:00 · repete semanal)
//   texto do card, recuado
const NIVEL_DE = Object.fromEntries(NIVEIS.map(([v, n]) => [norm(n), v]));
// cópia legível no WhatsApp (*negrito* = pasta, _itálico_ = etiqueta, ~riscado~ = feito); textoEmCards lê de volta
const dataBr = p => `${p.slice(8, 10)}/${p.slice(5, 7)}/${p.slice(0, 4)}` + (p.length > 10 ? " " + p.slice(11, 16) : "");
function cardsEmTexto(its) {
  const ordem = s => PASTAS.findIndex(([slug]) => slug === s), linhas = [];
  let atual = null;
  for (const i of [...its].sort((x, y) => ordem(pasta(x)) - ordem(pasta(y)))) {
    if (pasta(i) !== atual) { if (atual !== null) linhas.push(""); atual = pasta(i); linhas.push(`*${NOME[atual]}*`); }
    linhas.push(aberto(i) ? `☐ ${i.titulo}` : `✅ ~${i.titulo}~`);
    const meta = [i.tipo !== "tarefa" && i.tipo, nivel(i)[1], i.prazo_em && "📅 " + dataBr(i.prazo_em), REPETE[i.repete] && "🔁 " + REPETE[i.repete]].filter(Boolean);
    linhas.push(`    _${meta.join(" · ")}_`);
    for (const l of (i.detalhe || "").trim().split("\n")) if (l.trim()) linhas.push("    " + l);
  }
  return linhas.join("\n");
}
function lerMeta(s) {  // etiqueta (nova: _…_ recuada; antiga: entre parênteses); algo que não é do dumpbox: null
  const r = {}, partes = s.split(" · ").map(x => x.trim()), REP = Object.fromEntries(Object.entries(REPETE).map(([k, v]) => [v, k]));
  let d;
  for (const [k, t] of partes.entries()) {
    const n = norm(t), p = PASTAS.find(([, nome]) => norm(nome) === n);
    if (p) r.contexto = p[0];
    else if (TIPOS.includes(n)) r.tipo = n;
    else if (NIVEL_DE[n]) r.prioridade = NIVEL_DE[n];
    else if (/^prazo \d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$/.test(t)) r.prazo = t.slice(6).replace(" ", "T");
    else if ((d = t.match(/^📅 (\d{2})\/(\d{2})\/(\d{4})(?: (\d{2}:\d{2}))?$/))) r.prazo = `${d[3]}-${d[2]}-${d[1]}` + (d[4] ? "T" + d[4] : "");
    else if (/^repete (diario|semanal|mensal)$/.test(t)) r.repete = t.slice(7);
    else if (t.startsWith("🔁 ") && REP[t.slice(3)]) r.repete = REP[t.slice(3)];
    else if (!(k === 0 && partes.length > 1)) return null;  // 1º = pasta que não existe neste aparelho: vai para a atual
  }
  return r;
}
function textoEmCards(txt) {  // um card por linha; linha recuada (ou "> ") é etiqueta/texto do card de cima; *Pasta* muda a pasta
  const cards = [];
  let daPasta = null;
  for (const linha of txt.replace(/\r/g, "").split("\n")) {
    if (!linha.trim()) continue;
    const cab = linha.trim().match(/^\*([^*]+)\*$/);
    if (cab) { daPasta = PASTAS.find(([, nome]) => norm(nome) === norm(cab[1]))?.[0] || null; continue; }
    if (cards.length && /^(\s{2,}|\t|>)/.test(linha)) {
      const c = cards.at(-1), l = linha.replace(/^(\s{2,}|\t|>\s?)/, ""), e = l.match(/^_(.+)_$/), m = e && lerMeta(e[1]);
      if (m) Object.assign(c, m); else c.detalhe = (c.detalhe ? c.detalhe + "\n" : "") + l;
      continue;
    }
    const m = linha.trim().match(/^(?:[-*•]\s+)?(?:\[([ xX])\]\s+|(☐|☑️?|✅|✔️?)\s*)?(.*)$/);
    let titulo = m[3].trim().replace(/^~(.+)~$/, "$1"), meta = {};
    const p = titulo.match(/^(.*?)\s*\(([^()]*)\)$/), lido = p && p[1] && lerMeta(p[2]);
    if (lido) { titulo = p[1].trim(); meta = lido; }
    if (titulo) cards.push({ titulo: titulo.slice(0, 200), feito: (!!m[1] && m[1] !== " ") || (!!m[2] && m[2] !== "☐"), ...(daPasta && { contexto: daPasta }), ...meta });
  }
  return cards;
}
async function copiar(ids) {
  const its = doId(ids), txt = cardsEmTexto(its), s = its.length > 1 ? "s" : "";
  if (!its.length) return;
  try { await navigator.clipboard.writeText(txt); toast(`${its.length} card${s} copiado${s}. Cole aqui (Colar) ou em qualquer app.`); }
  catch { caixaTexto("Copiar", "Não consegui usar a área de transferência. Segure no texto e copie:", txt); }
}
async function colar(txt) {
  if (txt == null) {
    try { txt = await navigator.clipboard.readText(); }
    catch { return caixaTexto("Colar", "Cole aqui (segure e Colar). Um card por linha:", "", colar); }
  }
  const cards = textoEmCards(txt || "").slice(0, 200);
  if (!cards.length) return toast("Nada para colar: copie cards ou um texto (um card por linha).");
  const destino = NOME[vista] ? vista : "outro", feitos = [];
  let n = 0;
  for (const c of cards) {
    try {
      const r = await api("/api/itens", { titulo: c.titulo, contexto: c.contexto || destino, tipo: c.tipo || "tarefa", prioridade: c.prioridade || null,
        prazo: c.prazo || (vista === "hoje" ? "hoje" : null), repete: c.repete || null, detalhe: c.detalhe || null });
      n++; if (c.feito) feitos.push(r.id);
    } catch (e) { if (String(e.message) === "401") return; }
  }
  if (feitos.length) await api("/api/itens/editar", { ids: feitos, campo: "estado", valor: "feito" }).catch(() => {});
  toast(n === cards.length ? `${n} card${n > 1 ? "s" : ""} colado${n > 1 ? "s" : ""}` : `${n} de ${cards.length} cards colados (o resto deu erro)`);
  ultimo = ""; atualizar();
}
function caixaTexto(titulo, msg, valor, usar) {  // sem acesso à área de transferência: o texto numa caixa
  const t = el("textarea", "caixa"); t.value = valor; t.rows = 8;
  formulario(titulo, [el("p", "", msg), t], usar ? "Criar cards" : "Fechar", "ok", async () => usar && (() => usar(t.value)));
  t.focus(); if (valor) t.select();
}

// ---- tarefa criada à mão (sem IA) ----
function opcoes(s, lista, padrao) { for (const [v, t] of lista) { const o = el("option", "", t); o.value = v; s.append(o); } s.value = padrao; return s; }
function novaTarefa(it, tituloIni) {  // com it: edita o card (só manda o que mudou)
  dlgAberto = true; fecharMenu();
  const v = el("div", "veu"), f = el("form", "dlg nova"), fim = () => { v.remove(); f.remove(); dlgAberto = false; };
  const campo = (rot, ctl) => { const l = el("label"); l.append(el("span", "", rot), ctl); return l; };
  const titulo = el("input"); titulo.required = true; titulo.maxLength = 200; titulo.placeholder = "O que precisa fazer?";
  const pastaS = opcoes(el("select"), PASTAS, it ? pasta(it) : NOME[vista] ? vista : "casa");
  const tipo = opcoes(el("select"), TIPOS.map(t => [t, t]), it?.tipo || "tarefa");
  const crit = opcoes(el("select"), it ? NIVEIS.map(([v, n]) => [v, n]) : [["", "automática"], ...NIVEIS.map(([v, n]) => [v, n])], it?.prioridade || "");
  // prazo: calendário (dia + hora) ou texto ("sexta 14h"); o texto vence. Apagar o dia tira o prazo.
  const dia = el("input"), hora = el("input"), prazo = el("input");
  dia.type = "date"; hora.type = "time"; dia.setAttribute("aria-label", "Dia do prazo"); hora.setAttribute("aria-label", "Hora do prazo");
  dia.value = it?.prazo_em ? it.prazo_em.slice(0, 10) : !it && vista === "hoje" ? horaLocal().slice(0, 10) : "";
  hora.value = it?.prazo_em?.slice(11, 16) || "";
  prazo.maxLength = 60; prazo.placeholder = "ex.: sexta 14h, amanhã, dia 20";
  prazo.oninput = () => { if (prazo.value.trim()) dia.value = hora.value = ""; };
  dia.oninput = () => { prazo.value = ""; };
  hora.oninput = () => { prazo.value = ""; if (hora.value && !dia.value) dia.value = horaLocal().slice(0, 10); };
  const prazoFinal = () => prazo.value.trim() || (dia.value ? dia.value + (hora.value ? "T" + hora.value : "") : "");
  // texto livre + check-list editável (um campo por item; Enter cria o próximo, Backspace no vazio apaga). Grava tudo no `detalhe`.
  // ponytail: ao salvar, o texto vem primeiro e os itens depois (linhas misturadas perdem a ordem original)
  const linhasDet = (it?.detalhe || "").split("\n");
  const det = el("textarea"); det.maxLength = 2000; det.rows = 2; det.placeholder = "Detalhes, links… (opcional)";
  det.value = linhasDet.filter(l => !CHK.test(l)).join("\n").trim();
  const lista = el("div", "lst"), ckl = el("div", "ckl"), addLi = el("button", "addli", "+ item de check-list");
  const novoItem = (txt = "", marcado = false, foco = false, depois = null) => {
    const r = el("div", "li"), cb = el("input"), t = el("input"), x = el("button", "x", "×");
    cb.type = "checkbox"; cb.checked = marcado; cb.setAttribute("aria-label", "Feito");
    t.value = txt; t.maxLength = 200; t.placeholder = "item (Enter = próximo)";
    x.type = "button"; x.title = "Tirar item"; x.onclick = () => r.remove();
    t.onkeydown = e => {
      if (e.key === "Enter") { e.preventDefault(); novoItem("", false, true, r); }
      else if (e.key === "Backspace" && !t.value) { e.preventDefault(); const ant = r.previousElementSibling; r.remove(); (ant?.querySelector("input:not([type=checkbox])") || addLi).focus(); }
    };
    r.append(cb, t, x); depois ? depois.after(r) : lista.append(r);
    if (foco) t.focus();
  };
  for (const l of linhasDet) { const m = l.match(CHK); if (m) novoItem(m[2], m[1] !== " "); }
  addLi.type = "button"; addLi.onclick = () => novoItem("", false, true);
  ckl.append(el("span", "", "Check-list"), lista, addLi);
  const detFinal = () => [det.value.trim(), ...[...lista.children].map(r => [r.children[0].checked, r.children[1].value.trim()]).filter(([, t]) => t).map(([c, t]) => `[${c ? "x" : " "}] ${t}`)]
    .filter(Boolean).join("\n");
  const rep = opcoes(el("select"), [["", "não repete"], ...Object.entries(REPETE)], it?.repete || "");
  const lem = opcoes(el("select"), LEMBRETES, String(it?.lembrete ?? ""));
  titulo.value = it ? it.titulo || "" : tituloIni || "";
  const erro = el("p", "erro"), pe = el("div"), no = el("button", "no", "Cancelar"), si = el("button", "si ok", it ? "Salvar" : "Criar");
  no.type = "button"; no.onclick = fim; v.onclick = fim;
  f.onkeydown = e => { if (e.key === "Escape") fim(); };
  f.onsubmit = async e => {
    e.preventDefault(); si.disabled = true;
    try {
      if (it) {
        const m = { titulo: titulo.value, tipo: tipo.value, contexto: pastaS.value, prioridade: crit.value, prazo: prazoFinal(), repete: rep.value, detalhe: detFinal(), lembrete: lem.value };
        const antes = { titulo: it.titulo, tipo: it.tipo, contexto: pasta(it), prioridade: it.prioridade, prazo: it.prazo_em, repete: it.repete, detalhe: it.detalhe, lembrete: String(it.lembrete ?? "") };
        for (const k in m) if (m[k] === (antes[k] || "")) delete m[k];
        if (m.prazo === "") m.prazo = "limpar";  // tinha prazo e o dia foi apagado
        if (Object.keys(m).length) {
          const r = await api(`/api/itens/${it.id}/editar`, { mudancas: m });
          if (r.grupo) { (vistos ||= new Set()).add(r.grupo); toast(r.descricao, r.grupo); }
        }
        fim(); ultimo = ""; return atualizar();
      }
      const r = await api("/api/itens", { titulo: titulo.value, contexto: pastaS.value, tipo: tipo.value, prioridade: crit.value || null, prazo: prazoFinal() || null, repete: rep.value || null, detalhe: detFinal() || null, lembrete: lem.value === "" ? null : +lem.value });
      fim(); toast(r.descricao); sinal("criar"); ultimo = ""; atualizar();
    } catch (x) { si.disabled = false; erro.textContent = typeof x.detail === "string" ? x.detail : `Não consegui ${it ? "salvar" : "criar"}. O PC está ligado?`; }
  };
  const linha2 = el("div", "duas"); linha2.append(campo("Pasta", pastaS), campo("Tipo", tipo));
  const linha3 = el("div", "duas"); linha3.append(campo("Prazo: dia", dia), campo("hora (opcional)", hora));
  const linha4 = el("div", "duas"); linha4.append(campo("ou escreva o prazo", prazo), campo("Criticidade", crit));
  const semPrazo = el("button", "semprazo", "× tirar o prazo"); semPrazo.type = "button";  // salvar sem dia = "limpar" no servidor
  semPrazo.onclick = () => { dia.value = hora.value = prazo.value = ""; semPrazo.hidden = true; };
  semPrazo.hidden = !it?.prazo_em;
  dia.addEventListener("input", () => { semPrazo.hidden = !dia.value && !prazo.value.trim(); });
  const linha5 = el("div", "duas"); linha5.append(campo("Repetir (ao concluir, cria a próxima)", rep), campo("Lembrete", lem));
  pe.append(no, si);
  f.append(el("h4", "", it ? "Editar" : "Nova tarefa"), campo("Título", titulo), campo("Texto", det), ckl, linha2, linha3, semPrazo, linha4, linha5, erro, pe);
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
const botaoNova = () => botao("bnova", [el("b", "", "+"), "Nova"], "Nova tarefa com todos os campos (pasta, prazo, texto, check-list, repetir)", () => novaTarefa());
const botaoRapida = () => botao("brapida", [ic("bolt"), "Rápida"], "Criar várias seguidas: escreva e Enter (“@ sexta 14h” põe prazo)", abrirRapida);
// ---- criação rápida: o + abre uma linha no topo; Enter cria e limpa, pronta para a próxima ----
let rapida = null;
function abrirRapida() {
  if (!rapida) {
    const f = el("form", "rapida"), inp = el("input");
    inp.maxLength = 260; inp.placeholder = "Nova tarefa… Enter cria · “@ sexta 14h” põe prazo"; inp.setAttribute("aria-label", "Nova tarefa rápida");
    inp.onkeydown = e => { if (e.key === "Escape") fecharRapida(); };
    f.onsubmit = async e => {
      e.preventDefault();
      const [titulo, prazo] = inp.value.split(/\s+@\s*/, 2).map(s => s.trim());
      if (!titulo) return;
      try {
        const r = await api("/api/itens", { titulo, contexto: NOME[vista] ? vista : "outro", tipo: "tarefa", prazo: prazo || (vista === "hoje" ? "hoje" : null) });
        inp.value = ""; toast(r.descricao); sinal("criar"); ultimo = ""; atualizar();
      } catch (x) { if (String(x.message) !== "401") toast(typeof x.detail === "string" ? x.detail : "Não consegui criar. O PC está ligado?"); }
    };
    f.append(inp, botao("mais", ["mais opções"], "Formulário completo (pasta, texto, prazo no calendário, repetir)", () => { const t = inp.value; fecharRapida(); novaTarefa(null, t); }),
      botao("fx", [ic("x")], "Fechar", fecharRapida));
    for (const b of f.querySelectorAll("button")) b.type = "button";  // Enter envia o form, não clica "mais opções"
    rapida = f;
  }
  $("vista").querySelector(".hd")?.after(rapida);
  rapida.querySelector("input").focus();
}
function fecharRapida() { rapida?.remove(); rapida = null; }
const botaoColar = () => botao("bcolar", [ic("paste"), "Colar"], "Criar cards do que foi copiado (ou Ctrl+V fora da caixa)", () => colar());
const botaoSel = () => botao("bsel" + (modoSel ? " on" : ""), ["Selecionar"], "Selecionar vários (no PC: Ctrl+clique, Shift+clique, Ctrl+A)",
  e => { modoSel = !modoSel; if (!modoSel) sel.clear(); e.currentTarget.classList.toggle("on", modoSel); marcarSel(); });

// QR para o celular: abre o modo celular (Pages) já apontando para este PC; lá só falta a senha
const PAGES = "https://iambot1193.github.io/dumpbox/";
async function conectarCelular() {
  let r;
  try { r = await api("/api/endereco"); } catch { return toast("Não consegui perguntar ao PC o endereço do Tailscale."); }
  dlgAberto = true;
  const v = el("div", "veu"), d = el("div", "dlg"), fim = () => { v.remove(); d.remove(); dlgAberto = false; };
  const ok = el("button", "no", "Fechar"); ok.onclick = fim; v.onclick = fim;
  d.onkeydown = e => { if (e.key === "Escape") fim(); };
  d.append(el("h4", "", "Conectar celular"));
  if (r.url) {
    if (!window.qrcode) await new Promise((res, rej) => { const s = document.createElement("script"); s.src = "qrcode.js"; s.onload = res; s.onerror = rej; document.head.append(s); });
    const alvo = PAGES + "?pc=" + encodeURIComponent(r.url), q = qrcode(0, "M");
    q.addData(alvo); q.make();
    const img = el("div", "qr"); img.innerHTML = q.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
    d.append(el("p", "", "1. Celular com o Tailscale ligado, na mesma conta deste PC."),
      el("p", "", "2. Aponte a câmera para o código e abra o link."), el("p", "", "3. Digite a senha do dumpbox."), img,
      el("p", "", r.url));
  } else {
    d.append(el("p", "", r.erro));
    if (r.link) { const a = el("a", "", r.link); a.href = r.link; a.target = "_blank"; const p = el("p"); p.append(a); d.append(p); }
  }
  const pe = el("div"); pe.append(ok); d.append(pe);
  document.body.append(v, d); ok.focus();
}

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

// ---- arrastar: mouse na hora. Toque: segurar parado liga a seleção; segurar e mover arrasta ----
// Na lista do celular, soltar em cima de outro card troca os dois de lugar (vale também na grade do PC).
function trocar(a, b) {
  const pos = arranjar(gradeAtual), A = gradeAtual.find(i => i.id === a), B = gradeAtual.find(i => i.id === b);
  if (!A || !B) return;
  for (const i of gradeAtual) { const p = pos.get(i.id); Object.assign(i, { grade_col: p.col, grade_lin: p.lin }); }  // o resto fica onde está
  const pa = pos.get(a), pb = pos.get(b);
  Object.assign(A, { grade_col: pb.col, grade_lin: pb.lin }); Object.assign(B, { grade_col: pa.col, grade_lin: pa.lin });
  fixarGrade();
}
document.addEventListener("touchmove", e => { if (gesto) e.preventDefault(); }, { passive: false });
function arrastavel(card, it) {
  card.addEventListener("contextmenu", e => { if (matchMedia("(hover:none)").matches) e.preventDefault(); });
  card.addEventListener("pointerdown", ini => {
    const toque = ini.pointerType === "touch", noBotao = !!ini.target.closest("button");
    // card meio do celular é quase todo botão: no toque, deslizar pode começar em cima de um (segurar não)
    if (ini.button || ini.target.closest(".rs") || (noBotao && !toque)) return;
    if (ini.shiftKey && ini.pointerType === "mouse") return pincel(ini, it.id);  // Shift segurado: seleciona, não move
    const r = card.getBoundingClientRect();
    const grabX = ini.clientX - r.left, grabY = ini.clientY - r.top;
    let clone = null, alvo = null, ph = null, cel = null, timer = null, segurou = false, antes = null, desliza = false, dx = 0;
    const grid = matchMedia(AREA_GRADE).matches && gradeAtual ? card.closest(".grid") : null, t = tam(it);

    // faixa que aparece atrás do card ao deslizar: fraca até o ponto de concluir, cheia (e vibra) depois dele
    const lim = Math.min(110, r.width * .35);
    let faixa = null, passou = false;
    const rastro = x => {
      if (!faixa) {
        faixa = el("div", "rastro"); faixa.append(ic(aberto(it) ? "check" : "retry"), el("span", "", aberto(it) ? "feito" : "reabrir"));
        document.body.append(faixa);
      }
      faixa.style.cssText = `left:${r.left}px;top:${r.top}px;height:${r.height}px;width:${x}px`;
      if (x > lim !== passou) { passou = x > lim; faixa.classList.toggle("pronto", passou); if (passou && navigator.vibrate) navigator.vibrate(12); }
    };
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
    const segurar = () => {  // dedo parado: entra no modo Selecionar com este card
      segurou = gesto = true; fecharMenu();
      antes = { modo: modoSel, tinha: sel.has(it.id) };
      modoSel = true; sel.add(it.id); ancora = it.id; marcarSel();
      if (navigator.vibrate) navigator.vibrate(15);
    };
    const mover = e => {
      if (!clone) {
        const dist = Math.hypot(e.clientX - ini.clientX, e.clientY - ini.clientY);
        if (toque && !segurou) {
          dx = e.clientX - ini.clientX;
          // deslizar para a direita (antes de segurar) conclui ou reabre o card
          if (!desliza && dx > 12 && dx > Math.abs(e.clientY - ini.clientY) * 1.5) { desliza = gesto = true; clearTimeout(timer); card.classList.add("desliza"); }
          if (desliza) { card.style.transform = `translateX(${Math.max(0, dx)}px)`; rastro(Math.max(0, dx)); return; }
          if (dist > 10) limpar();  // mexeu antes de segurar: é rolagem
          return;
        }
        if (dist < (toque ? 10 : 5)) return;
        if (toque && !antes.tinha) { sel.delete(it.id); modoSel = antes.modo; marcarSel(); }  // segurou para arrastar, não para selecionar
        comecar();
      }
      if (toque) { if (e.clientY < 70) scrollBy(0, -12); else if (e.clientY > innerHeight - 70) scrollBy(0, 12); }  // ponytail: rola só enquanto o dedo mexe
      clone.style.left = e.clientX - grabX + "px"; clone.style.top = e.clientY - grabY + "px";
      const sob = document.elementFromPoint(e.clientX, e.clientY);
      const outro = !grid && gradeAtual && sob?.closest("#vista article.c[data-id]");
      marcar(sob?.closest("[data-alvo]") || (outro && outro !== card ? outro : null));
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
      clone?.remove(); ph?.remove(); faixa?.remove(); alvo?.classList.remove("over"); card.classList.remove("saiu", "desliza"); card.style.transform = "";
      document.body.style.cursor = "";
      gesto = false;
    };
    const cancelar = () => limpar();
    const soltar = () => {
      const a = alvo?.dataset.alvo, troca = alvo?.dataset.id, c = cel, ativo = !!clone, conclui = desliza && dx > lim, fx = conclui ? faixa : null;
      if (conclui) faixa = null;  // a faixa fica para a animação de saída
      limpar();
      if (segurou || desliza) semClique = performance.now() + 300;
      if (conclui) {  // card sai pela direita com a faixa cheia; depois salva (o redesenho tira o card)
        gesto = true;
        card.style.transform = `translateX(${dx}px)`; card.getBoundingClientRect();
        card.style.transition = "transform .2s ease-in, opacity .2s"; card.style.transform = `translateX(${innerWidth}px)`; card.style.opacity = "0";
        fx.style.transition = "width .2s ease-in"; fx.style.width = innerWidth - r.left + "px";
        setTimeout(() => {
          fx.remove(); gesto = false;
          editar(it.id, "estado", aberto(it) ? "feito" : "catalogado")
            .finally(() => { if (card.isConnected) card.style.transition = card.style.transform = card.style.opacity = ""; });  // deu erro: volta
        }, 230);
        return;
      }
      if (desliza) return;
      if (!ativo) return;
      if (troca) return trocar(it.id, +troca);
      arrastou = true; setTimeout(() => { arrastou = false; }, 0);  // o clique que vem depois do soltar não seleciona
      const ids = sel.has(it.id) && sel.size > 1 ? [...sel] : [it.id];
      if (ids.length > 1 && a) limparSel();
      if (a === "lixeira") editar(ids, "estado", "arquivado");
      else if (a && (ids.length > 1 || a !== pasta(it))) editar(ids, "contexto", a);
      else if (c) fixarGrade(c);
    };
    document.addEventListener("pointermove", mover); document.addEventListener("pointerup", soltar); document.addEventListener("pointercancel", cancelar);
    if (toque && !noBotao) timer = setTimeout(segurar, 350);
  });
}
function redimensionavel(alca, card, it, p) {
  alca.addEventListener("pointerdown", ini => {
    ini.stopPropagation(); ini.preventDefault();
    gesto = true; fecharMenu();
    if (!matchMedia(AREA_GRADE).matches) return redimCelular(ini, card, it, p);
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

// celular: grade de 2 colunas. Puxar o canto para a direita = inteiro, para a esquerda = meio; para baixo/cima = altura 1-4.
// ponytail: o tamanho é o mesmo do PC (inteiro no celular = largura ≥2 lá); tamanho separado por tela se incomodar
function redimCelular(ini, card, it, p) {
  const etiqueta = el("span", "tamanho");
  let larg = p.larg > 1 ? 2 : 1, alt = p.alt;
  const previa = () => { card.classList.toggle("w2", larg === 2); card.style.setProperty("--h", alt); etiqueta.textContent = `${larg === 2 ? "inteiro" : "meio"} × ${alt}`; };
  card.classList.add("rsz"); card.append(etiqueta); previa();
  const mover = e => {
    const dx = e.clientX - ini.clientX, dy = e.clientY - ini.clientY;
    const l = dx > 30 ? 2 : dx < -30 ? 1 : (p.larg > 1 ? 2 : 1), a = Math.min(4, Math.max(1, p.alt + Math.round(dy / 92)));
    if (l !== larg || a !== alt) { larg = l; alt = a; previa(); }
  };
  const soltar = () => {
    document.removeEventListener("pointermove", mover); document.removeEventListener("pointerup", soltar); document.removeEventListener("pointercancel", soltar);
    etiqueta.remove(); card.classList.remove("rsz"); gesto = false; semClique = performance.now() + 300;
    const L = larg === 2 ? Math.max(2, p.larg) : 1;
    if (L !== p.larg || alt !== p.alt) fixarGrade({ id: it.id, col: Math.min(p.col, COLS - L + 1), lin: p.lin, larg: L, alt });
    else { ultimo = ""; render(); }
  };
  document.addEventListener("pointermove", mover); document.addEventListener("pointerup", soltar); document.addEventListener("pointercancel", soltar);
}

// ---- desenho ----
const CHK = /^\s*(?:[-*]\s*)?\[([ xX])\]\s*(.*)$/;
function textoCard(it) {  // texto do card; linhas "[ ] item" viram check-list marcável (grava no próprio texto, sem aviso)
  const d = el("div", "det"), linhas = it.detalhe.split("\n");
  let feitos = 0, total = 0;
  linhas.forEach((l, k) => {
    const m = l.match(CHK);
    if (!m) return d.append(el("span", "", l + "\n"));
    const marcado = m[1] !== " ", lb = el("label", "chk"), cb = el("input");
    total++; feitos += marcado;
    cb.type = "checkbox"; cb.checked = marcado;
    lb.onclick = e => e.stopPropagation();  // marcar não seleciona o card
    cb.onchange = async () => {
      const novo = [...linhas]; novo[k] = l.replace(/\[[ xX]\]/, cb.checked ? "[x]" : "[ ]");
      try { const r = await api(`/api/itens/${it.id}/editar`, { mudancas: { detalhe: novo.join("\n") } }); if (r.grupo) (vistos ||= new Set()).add(r.grupo); }
      catch { cb.checked = !cb.checked; return toast("Não consegui salvar. O PC está ligado?"); }
      ultimo = ""; atualizar();
    };
    lb.append(cb, el("span", "", m[2])); d.append(lb);
  });
  if (total) { d.classList.add("lista"); d.prepend(el("small", "cont" + (feitos === total ? " ok" : ""), `☑ ${feitos}/${total}`)); }
  return d;
}
function cartao(it, comPasta) {
  const a = el("article", `c t-${it.tipo || "nota"} ${nivel(it)[0]} ${it.estado}${sel.has(it.id) ? " sel" : ""}`);
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
  if (it.detalhe) a.append(textoCard(it));
  if (atrasado(it)) {
    const n = -dias(it.prazo_em), chip = el("span", "chip"), d = el("div", "due");
    chip.append(ic("alert"), `atrasado ${n} dia${n > 1 ? "s" : ""}`); d.append(chip); a.append(d);
  } else if (it.prazo_em) {
    const d = el("div", "due"); d.append(ic("clock"), txtPrazo(it.prazo_em)); a.append(d);
  }
  if (REPETE[it.repete]) { const d = el("div", "due"); d.append(ic("retry"), REPETE[it.repete]); a.append(d); }
  if (it.prazo_em && it.lembrete != null) a.append(el("div", "due", "🔔 " + (LEMBRETES.find(([v]) => v === String(it.lembrete))?.[1] || `${it.lembrete} min antes`)));
  const acts = el("div", "acts"), dir = el("div");
  const feito = aberto(it);
  dir.append(botao("cp", [ic("copy")], "Copiar", () => copiar(it.id)), botao("ed", [ic("edit")], "Editar", () => novaTarefa(it)),botao("mv", [ic("move")], "Mover para…", e => menuMover(e.currentTarget, it.id)),
    botao("tr", [ic("trash")], "Excluir", () => editar(it.id, "estado", "arquivado")));
  acts.append(botao("ok", [ic(feito ? "check" : "retry")], feito ? "Marcar como feito" : "Reabrir", () => {
    if (!feito) return editar(it.id, "estado", "catalogado");
    a.classList.add("concluindo");  // risca, brilha e some; depois grava (falhou: o card volta)
    setTimeout(() => editar(it.id, "estado", "feito").finally(() => a.classList.remove("concluindo")), 420);
  }), dir);
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
  v.append(cabecalho("Hoje", `${n} aberto${n === 1 ? "" : "s"} em ${ps} pasta${ps === 1 ? "" : "s"} · ${SEMANA[d.getDay()]}, ${d.getDate()}/${d.getMonth() + 1}`, botaoNova(), botaoRapida(), botaoColar(), botaoSel(), chaveFeitos(feitos)));
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
  const hd = cabecalho(NOME[vista], `${abertos.length} aberto${abertos.length === 1 ? "" : "s"}${crit ? ` · ${crit} crítica${crit === 1 ? "" : "s"}` : ""} · ${altas} alta${altas === 1 ? "" : "s"}`, botaoNova(), botaoRapida(), botaoColar(), botaoSel(), ft, chaveFeitos(todos.length - abertos.length));
  // "Apagar pasta" vai junto do título (não empurra a barra de botões para outra linha)
  if (vista !== "outro") hd.querySelector("h2 + span").after(botao("perigo", ["Apagar pasta"], "Apagar esta pasta (os itens vão para outra)", () => apagarPasta(vista)));
  v.append(hd);
  if (!lista.length) { v.append(el("p", "vazio", filtro ? "Nada com essa criticidade." : "Pasta vazia.")); gradeAtual = null; return; }
  gradeAtual = lista;
  const pos = arranjar(lista), g = el("div", "grid");
  const emOrdem = [...lista].sort((a, b) => pos.get(a.id).lin - pos.get(b.id).lin || pos.get(a.id).col - pos.get(b.id).col);
  for (const i of emOrdem) {
    const p = pos.get(i.id), c = cartao(i);
    c.style.gridColumn = `${p.col}/span ${p.larg}`; c.style.gridRow = `${p.lin}/span ${p.alt}`;
    if (p.larg > 1) c.classList.add("w2");
    c.style.setProperty("--h", p.alt);  // celular: 2 colunas (w2 = inteiro), altura em linhas
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
function vBusca(v) {  // todas as palavras, sem acento, em qualquer pasta; feitos no fim
  const ps = norm($("busca").value).split(/\s+/).filter(Boolean);
  const l = D.itens.filter(i => { const t = norm(`${i.titulo} ${i.detalhe || ""} ${NOME[pasta(i)] || ""} ${i.tipo}`); return ps.every(p => t.includes(p)); })
    .sort((a, b) => aberto(b) - aberto(a) || urgencia(a, b));
  v.append(cabecalho("Busca", `${l.length} ite${l.length === 1 ? "m" : "ns"} para “${$("busca").value.trim()}”`));
  if (!l.length) return v.append(el("p", "vazio", "Nada encontrado."));
  const g = el("div", "grid");
  for (const i of l) { const c = cartao(i, true); c.style.gridColumn = "span 1"; c.style.setProperty("--l", 2); g.append(c); }
  v.append(g);
}
$("busca").addEventListener("input", () => { sel.clear(); render(); });
function ir(v) { $("busca").value = ""; vista = v; filtro = null; sel.clear(); ancora = null; modoSel = false; try { localStorage.setItem(VISTA, v); } catch {} render(); scrollTo(0, 0); }
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
  if (window.DUMPBOX_PC) {  // celular conectado: selo com o nome do PC (sem rede, o aviso do topo diz "sem conexão")
    const s = el("span", "pcok", "PC: " + window.DUMPBOX_PC.replace(/^https?:\/\//, "").split(".")[0]);
    s.title = "Conectado a " + window.DUMPBOX_PC; logo.append(s);
  }
  const hoje = [ic("sun"), "Hoje"];
  if (atras) hoje.push(el("span", "chip", `${atras} atrasado${atras > 1 ? "s" : ""}`));
  const lb = el("div", "lb"); lb.append(el("span", "", "PASTAS"), el("span", "", "abertos"));
  const fim = el("div", "fim");
  fim.append(linha("revisar", [ic("alert"), "Revisar"], D.revisar.filter(c => c.status === "falhou").length),
    linha("lixeira", [ic("trash"), "Lixeira"], D.lixeira.length, true),
    ...(temAvisos && Notification.permission === "default" ? [botao("sair", ["ligar avisos"], "Notificar quando uma tarefa passar do prazo", ativarAvisos)] : []),
    botao("sair mais", ["⋯ mais"], "Avisos, ajuda, sair", e => { const a = e.currentTarget; popover(a, "Mais", [
      { txt: "Avisos", fn: () => menuAvisos(a) },
      { txt: "Ajuda", fn: () => tutorial() },
      ...(window.DUMPBOX_LOCAL ? [] : [{ txt: "Conectar celular", fn: conectarCelular }, { txt: "Cópia p/ celular", fn: () => { location.href = "api/copia"; } }]),
      ...(window.DUMPBOX_PC ? [{ txt: "Desconectar do PC", fn: () => window.DUMPBOX_DESCONECTAR() }] : []),
      { txt: "Sair", fn: async () => { try { localStorage.removeItem(COPIA); } catch {} await api("/api/logout", {}); mostra("login"); } },
    ]); }));
  $("nav").replaceChildren(logo, linha("hoje", hoje, base.length), lb,
    ...PASTAS.map(([p, n]) => linha(p, [n], abertos.filter(i => pasta(i) === p).length, true)),
    botao("fold mais", [el("span", "nm", "+"), el("span", "rot", "Nova pasta")], "Criar pasta", novaPasta), fim);
}
function render() {
  gradeAtual = null;
  desenhaNav();
  const v = $("vista"), foco = rapida && document.activeElement === rapida.firstChild;  // a linha rápida sobrevive ao redesenho, com o foco
  v.replaceChildren();
  if (norm($("busca").value).trim()) vBusca(v);
  else if (vista === "hoje") vHoje(v);
  else if (vista === "revisar") vRevisar(v);
  else if (vista === "lixeira") vLixeira(v);
  else if (NOME[vista]) vPasta(v);
  else return ir("hoje");
  if (rapida) { v.querySelector(".hd")?.after(rapida); if (foco) rapida.firstChild.focus(); }
  const naTela = new Set(cardsVisiveis().map(c => +c.dataset.id));
  for (const id of sel) if (!naTela.has(id)) sel.delete(id);
  marcarSel();
}
function avisos(alts) {
  if (!vistos) { vistos = new Set(alts.map(a => a.grupo)); return; }
  for (const a of alts) if (!vistos.has(a.grupo)) {  // instrução digitada na caixa, aplicada pelo worker
    vistos.add(a.grupo);
    if (!a.desfeito) toast(a.descricoes.slice(0, 2).join(" · ") + (a.descricoes.length > 2 ? ` · e mais ${a.descricoes.length - 2}` : ""), a.grupo, "mudanca");
  }
}
async function atualizar() {
  try {
    const [r, alts] = await Promise.all([api("/api/itens"), api("/api/alteracoes")]);
    avisos(alts);
    const s = JSON.stringify(r);
    if (gesto || menuAberto || dlgAberto) return;  // não redesenha no meio de um arraste ou menu
    if (s !== ultimo) {
      ultimo = s; D = r; lerAlt().forEach(aplicaLocal); guardaCopia();  // o que ainda não subiu continua na tela
      if (r.pastas?.length) { PASTAS = r.pastas.map(p => [p.slug, p.nome]); NOME = Object.fromEntries(PASTAS); }
      render();
    }
    mostrarFila(); avisarVencidos();
  } catch (e) {
    if (e instanceof TypeError && !ultimo && !(gesto || menuAberto || dlgAberto)) {  // sem o PC: mostra a última cópia
      if (!D.itens.length) try { const cp = JSON.parse(localStorage.getItem(COPIA)); if (cp?.itens) D = cp; } catch {}
      if (D.pastas?.length) { PASTAS = D.pastas.map(p => [p.slug, p.nome]); NOME = Object.fromEntries(PASTAS); }
      ultimo = "copia"; render(); mostrarFila();
    } else if (!/^(401|Failed to fetch)/.test(e.message)) console.error("atualizar:", e);
  }
}

// ---- avisos de tarefa vencida: notificação do navegador quando o prazo passa ----
// ponytail: checa a cada atualização (5 s), então só avisa com o app aberto ou em segundo plano; app fechado
// não avisa. Para isso: Web Push (VAPID) no servidor ou o Telegram da fase 3.
const AVISADOS = "dumpbox.avisados", temAvisos = "Notification" in window;
const vencido = i => aberto(i) && i.prazo_em && (dias(i.prazo_em) < 0 || (i.prazo_em.length > 10 && i.prazo_em <= horaLocal().slice(0, 16)));
async function ativarAvisos() {
  if (!temAvisos) return toast("Este navegador não tem notificações. No iPhone: instale o app na tela inicial.");
  const p = await Notification.requestPermission();
  toast(p === "granted" ? "Avisos ligados: tarefa que passar do prazo vira notificação." : "Avisos bloqueados. Libere as notificações nas configurações do site.");
  render(); avisarVencidos();
}
async function avisarVencidos() {
  if (!temAvisos || Notification.permission !== "granted") return;
  let ja = {}; try { ja = JSON.parse(localStorage.getItem(AVISADOS) || "{}"); } catch {}
  const novos = D.itens.filter(i => vencido(i) && ja[i.id] !== i.prazo_em);  // mudou o prazo: avisa de novo
  if (!novos.length) return;
  const agora = Object.fromEntries(D.itens.filter(vencido).map(i => [i.id, i.prazo_em]));
  try { localStorage.setItem(AVISADOS, JSON.stringify(agora)); } catch { return; }  // sem guardar, avisaria a cada 5 s
  notificar(novos.length === 1 ? "Tarefa vencida" : `${novos.length} tarefas vencidas`, listaAviso(novos), "dumpbox-vencidas");
}
const listaAviso = its => its.slice(0, 4).map(i => `• ${i.titulo} (${txtPrazo(i.prazo_em)})`).join("\n") + (its.length > 4 ? `\n… e mais ${its.length - 4}` : "");
async function notificar(titulo, corpo, tag) {  // sem permissão de notificação: aviso na tela (só com o app aberto)
  bipe();
  if (!temAvisos || Notification.permission !== "granted") return toast(`${titulo}: ${corpo.replace(/\n/g, " ")}`);
  try {
    const reg = await navigator.serviceWorker?.getRegistration();  // Android só mostra pelo service worker
    if (reg) return await reg.showNotification(titulo, { body: corpo, tag, icon: "icon.svg" });
  } catch {}
  try { new Notification(titulo, { body: corpo, tag }); } catch {}
}
let audio;
function bipe() {  // som gerado na hora, sem arquivo; o navegador só toca depois de algum toque na página
  if (!CFG.som) return;
  try {
    audio ||= new AudioContext();
    const o = audio.createOscillator(), g = audio.createGain(), t = audio.currentTime;
    o.frequency.value = 880; g.gain.setValueAtTime(.2, t); g.gain.exponentialRampToValueAtTime(.001, t + .35);
    o.connect(g).connect(audio.destination); o.start(t); o.stop(t + .35);
  } catch {}
}
// lembrete por tarefa (X min antes do prazo) e lembrete diário (lista do dia num horário). Mesmo limite dos vencidos:
// ponytail: só com o app aberto ou em 2º plano; app fechado precisa de Web Push ou do Telegram
const LEMBRADOS = "dumpbox.lembrados";
const alvoLembrete = i => new Date(new Date(i.prazo_em.length > 10 ? i.prazo_em : i.prazo_em + "T09:00") - i.lembrete * 6e4);  // só dia = 9h
function lembrar() {
  let ja = {}; try { ja = JSON.parse(localStorage.getItem(LEMBRADOS) || "{}"); } catch {}
  const agora = new Date(), hoje = horaLocal().slice(0, 10), chave = i => `${i.prazo_em}|${i.lembrete}`;
  const hora = D.itens.filter(i => aberto(i) && i.prazo_em && i.lembrete != null && ja[i.id] !== chave(i)
    && alvoLembrete(i) <= agora && agora - alvoLembrete(i) < 12 * 36e5);  // muito atrasado: o aviso de vencida já cobre
  const diario = CFG.diario && horaLocal().slice(11, 16) >= CFG.diario && ja.diario !== hoje;
  if (!hora.length && !diario) return;
  hora.forEach(i => { ja[i.id] = chave(i); });
  if (diario) ja.diario = hoje;
  try { localStorage.setItem(LEMBRADOS, JSON.stringify(ja)); } catch { return; }  // sem guardar, repetiria a cada 5 s
  if (hora.length) notificar(hora.length === 1 ? `Lembrete: ${hora[0].titulo}` : `${hora.length} lembretes`, listaAviso(hora), "dumpbox-lembrete");
  if (diario) {
    const hj = D.itens.filter(i => aberto(i) && i.prazo_em && dias(i.prazo_em) <= 0);
    notificar(hj.length ? `Hoje: ${hj.length} com prazo` : "Hoje: nada com prazo", hj.length ? listaAviso(hj) : "Dia livre no dumpbox.", "dumpbox-diario");
  }
}

// ---- tutorial guiado: abre sozinho no 1º acesso (depois pelo "ajuda"); destaca a parte da tela e espera você fazer ----
const TOUR = "dumpbox.tour";
const PASSOS = [  // [alvo, título, texto, ação que avança (sem ação: botão Próximo)]
  ["#txt", "Despeje uma nota", "Escreva qualquer coisa na caixa e toque Guardar. Com o PC, a IA separa em tarefas, prazos e pastas. O microfone dita por voz.", "guardar"],
  [".brapida", "Criar rápido", "Toque Rápida e escreva uma tarefa. Enter cria e já deixa a linha pronta para a próxima. “@ sexta 14h” põe prazo.", "criar"],
  ["#vista .c .ok", "Concluir", "Toque ✓ num card, ou deslize o card para a direita.", "feito"],
  [".bsel", "Vários de uma vez", "No celular: segure o dedo num card e toque nos outros. No PC: Ctrl+clique. A barra de baixo conclui, copia, move ou exclui. Copiar gera texto pronto para o WhatsApp; Colar cria cards de qualquer texto."],
  ["#nav", "Pastas e Hoje", "A lateral tem as pastas. Hoje junta o que vence hoje e o que está atrasado. No texto do card, linhas “[ ] item” viram check-list. No celular, puxe o canto do card para mudar o tamanho."],
  [null, "Avisos", "Ligue os avisos para receber uma notificação quando uma tarefa passar do prazo (com o app aberto ou em segundo plano)."],
];
let tour = null;  // a tela continua usável: só um destaque (furo no escuro, sem bloquear o toque) e um balão
function tutorial(k = 0) {
  fimTutorial(false); fecharMenu();
  const [alvoSel, titulo, texto, espera] = PASSOS[k], ult = k === PASSOS.length - 1;
  const furo = el("div", "furo"), b = el("div", "dlg tour"), pe = el("div");
  const fim = () => fimTutorial(true);
  pe.append(botao("no", [ult ? "Fechar" : "Sair"], null, fim));
  if (ult && temAvisos && Notification.permission === "default") pe.append(botao("si ok", ["Ligar avisos"], null, () => { fim(); ativarAvisos(); }));
  if (!ult) pe.append(botao(espera ? "no" : "si ok", [espera ? "Pular passo" : "Próximo"], null, () => tutorial(k + 1)));
  b.append(el("small", "passo", `${k + 1} de ${PASSOS.length}`), el("h4", "", titulo), el("p", "", texto));
  if (espera) b.append(el("small", "espera", "Faça na tela para continuar"));
  b.append(pe);
  document.body.append(furo, b);
  tour = { k, furo, b, espera, raf: 0 };
  const seguir = () => {  // acompanha o alvo (rolagem, redesenho, teclado do celular)
    if (tour?.furo !== furo) return;
    const alvo = alvoSel && [...document.querySelectorAll(alvoSel)].find(e => e.getClientRects().length);
    if (alvo) {
      const r = alvo.getBoundingClientRect();
      Object.assign(furo.style, { display: "block", left: r.left - 4 + "px", top: r.top - 4 + "px", width: r.width + 8 + "px", height: r.height + 8 + "px" });
      b.classList.toggle("cima", r.top + r.height / 2 > innerHeight / 2);
    } else furo.style.display = "none";
    tour.raf = requestAnimationFrame(seguir);
  };
  seguir();
}
function fimTutorial(visto) {
  if (tour) { cancelAnimationFrame(tour.raf); tour.furo.remove(); tour.b.remove(); tour = null; }
  if (visto) try { localStorage.setItem(TOUR, "1"); } catch {}
}
function sinal(acao) {  // a tela avisa o que o usuário fez; se era o que o passo pedia, avança
  if (!tour || tour.espera !== acao) return;
  const k = tour.k; tour.espera = null;
  tour.b.querySelector(".espera").textContent = "Boa! ✓";
  setTimeout(() => { if (tour?.k === k) tutorial(k + 1); }, 700);
}

// ---- captura ----
const crescer = () => { const t = $("txt"); t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; };
$("txt").addEventListener("input", crescer);
$("txt").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $("guardar").click(); } });
$("guardar").onclick = async () => {
  const texto = $("txt").value.trim(); if (!texto && !anexo) return;
  const f = lerFila(); f.push(anexo ? { id: uuid(), imagem: anexo, texto, criado_em: horaLocal() } : { id: uuid(), texto, criado_em: horaLocal() });
  if (!gravaFila(f)) { toast("Sem espaço para guardar a foto offline. Envie com o PC ligado."); return; }
  if (anexo) toast("Foto enviada: a IA lê a lista e cria os itens (pode levar 1 min).");
  $("txt").value = ""; anexar(null); crescer(); await enviarFila(); sinal("guardar"); atualizar();
};

// ditado: reconhecimento de voz do próprio navegador (Chrome manda o áudio para o serviço do Google)
const Voz = window.SpeechRecognition || window.webkitSpeechRecognition;
let ouvindo = null;
$("voz").hidden = !Voz;
$("voz").onclick = () => {
  if (ouvindo) return ouvindo.stop();
  const r = ouvindo = new Voz();
  r.lang = "pt-BR"; r.interimResults = false; r.continuous = false;
  r.onresult = e => {
    const fala = [...e.results].map(x => x[0].transcript).join(" ").trim(), t = $("txt");
    if (fala) { t.value = t.value.trim() ? `${t.value.trimEnd()}\n${fala}` : fala; crescer(); }
  };
  r.onerror = e => { if (e.error !== "aborted" && e.error !== "no-speech") toast(e.error === "not-allowed" ? "Libere o microfone para ditar." : "Não consegui ouvir. Tente de novo."); };
  r.onend = () => { ouvindo = null; $("voz").classList.remove("on"); };
  $("voz").classList.add("on"); r.start();
};

// compartilhar para o dumpbox (Android: menu Compartilhar) e atalho "Nova nota" do ícone: preenchem a caixa
{
  const q = new URLSearchParams(location.search), veio = [...new Set(["title", "text", "url"].map(k => q.get(k)).filter(Boolean))];
  if (veio.length || q.has("nova")) {
    if (veio.length) { $("txt").value = veio.join("\n"); crescer(); }
    ["title", "text", "url", "nova"].forEach(k => q.delete(k));
    history.replaceState(null, "", location.pathname + (q.toString() ? "?" + q : ""));
    setTimeout(() => $("txt").focus(), 300);
  }
}

// foto de lista: reduz no navegador (lado maior 1280 px, JPEG) e entra na mesma fila das notas
async function reduzir(arq) {
  const bmp = await createImageBitmap(arq), k = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
  const cv = document.createElement("canvas"); cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
  cv.getContext("2d").drawImage(bmp, 0, 0, cv.width, cv.height);
  return cv.toDataURL("image/jpeg", 0.85).split(",")[1];
}
$("foto").querySelector("input").onchange = e => { const arq = e.target.files[0]; e.target.value = ""; if (arq) enviarFoto(arq); };
// Ctrl+V de print (Win+Shift+S) em qualquer lugar da tela, menos na caixa da IA; texto colado segue normal
document.addEventListener("paste", e => {
  if (e.target.closest?.(".ai-in")) return;
  const arq = [...(e.clipboardData?.items || [])].find(i => i.kind === "file" && i.type.startsWith("image/"))?.getAsFile();
  if (arq) { e.preventDefault(); enviarFoto(arq); return; }
  // texto colado fora de qualquer caixa: vira cards na pasta aberta
  const txt = e.clipboardData?.getData("text/plain");
  if (txt && !e.target.closest?.("input,textarea,[contenteditable]") && !dlgAberto && !$("app").hidden) { e.preventDefault(); colar(txt); }
});
// foto não vai sozinha: fica anexada (miniatura) até o Guardar, junto com o que for escrito como instrução
let anexo = null;
function anexar(b64) {
  anexo = b64;
  const a = $("anexo"); a.hidden = !b64;
  if (b64) a.querySelector("img").src = "data:image/jpeg;base64," + b64;
  $("txt").placeholder = b64 ? "Instruções para a foto (opcional): “tudo do trabalho, pra sexta”…" : "Despeje tudo aqui, solto, misturado…";
}
$("anexo").querySelector("button").onclick = () => { anexar(null); $("txt").focus(); };
async function enviarFoto(arq) {
  try { anexar(await reduzir(arq)); } catch { toast("Não consegui abrir essa imagem."); return; }
  $("txt").focus();
}

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
  mostra("app"); await enviarFila(); await atualizar();  // desenha antes do tutorial: com diálogo aberto atualizar() não redesenha
  let visto = "1"; try { visto = localStorage.getItem(TOUR); } catch {}
  if (!visto) tutorial();
}
window.addEventListener("online", () => { enviarFila().then(atualizar); });
setInterval(() => { if (!$("app").hidden) { enviarFila(); atualizar(); lembrar(); } }, 5000);  // lembrar fora do atualizar: vale sem o PC
setInterval(() => { if (!$("prep").hidden) estado(); }, 3000);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
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
