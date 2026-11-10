// PWA: fila local de capturas (localStorage) -> envia ao servidor quando houver conexão.
// Todo texto vindo do servidor entra via textContent (nunca innerHTML).
const $ = id => document.getElementById(id);
const FILA = "dumpbox.fila";
const lerFila = () => { try { return JSON.parse(localStorage.getItem(FILA) || "[]"); } catch { return []; } };
const gravaFila = f => { try { localStorage.setItem(FILA, JSON.stringify(f)); } catch {} };
const uuid = () => crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);

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
async function estado() {
  try {
    const e = await (await fetch("/api/estado")).json();
    const p = e.preparo, el = $("prep");
    el.hidden = p.pronto;
    if (!p.pronto) el.textContent = p.erro ? `Erro ao preparar a IA: ${p.erro}` : `Preparando a IA (só na primeira vez): ${p.msg || "aguarde"} ${p.pct ? p.pct + "%" : ""}`;
    return e;
  } catch { return null; }
}

async function enviarFila() {
  let fila = lerFila();
  for (const n of [...fila]) {
    try { await api("/api/capturas", n); fila = fila.filter(x => x.id !== n.id); gravaFila(fila); }
    catch (e) { if (String(e.message) === "401") return; break; }
  }
  const q = lerFila().length;
  $("st").textContent = q ? `${q} nota(s) na fila, aguardando o servidor` : "";
}

function linha(it) {
  const d = document.createElement("div");
  d.className = `item ${it.prioridade || ""} ${it.estado}`;
  const t = document.createElement("div"); t.className = "t";
  t.textContent = it.titulo;
  const m = document.createElement("div"); m.className = "m";
  m.textContent = [it.tipo, it.contexto, it.prazo_em].filter(Boolean).join(" · ");
  t.appendChild(m);
  const b = document.createElement("button"); b.className = "sec";
  b.textContent = it.estado === "feito" ? "↺" : "✓";
  b.onclick = async () => { await api(`/api/itens/${it.id}/estado`, { estado: it.estado === "feito" ? "catalogado" : "feito" }); atualizar(); };
  d.append(t, b);
  return d;
}

async function atualizar() {
  try {
    const { itens, revisar } = await api("/api/itens");
    const el = $("lista"); el.replaceChildren();
    const grupo = (titulo, nos) => { if (!nos.length) return; const h = document.createElement("h2"); h.textContent = titulo; el.append(h, ...nos); };
    grupo("Revisar", revisar.map(c => { const d = document.createElement("div"); d.className = "item"; d.textContent = `${c.status === "pendente" ? "⏳" : "⚠️"} ${c.texto}`; return d; }));
    const porCtx = {};
    for (const it of itens) (porCtx[it.contexto || "outro"] ||= []).push(it);
    for (const [ctx, lst] of Object.entries(porCtx)) grupo(ctx, lst.map(linha));
  } catch {}
}

$("guardar").onclick = async () => {
  const texto = $("txt").value.trim(); if (!texto) return;
  const f = lerFila(); f.push({ id: uuid(), texto }); gravaFila(f);
  $("txt").value = ""; await enviarFila(); atualizar();
};
$("entrar").onclick = async () => {
  try { await api("/api/login", { senha: $("senha").value }); $("senha").value = ""; $("err").textContent = ""; iniciar(); }
  catch { $("err").textContent = "senha incorreta ou muitas tentativas"; }
};
$("sair").onclick = async () => { await api("/api/logout", {}); mostra("login"); };

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

// ---- Chat: o servidor PROPÕE ações; nada muda até clicar em Confirmar ----
const hist = [];
function aba(n) {
  $("aba-notas").hidden = n !== "notas"; $("aba-chat").hidden = n !== "chat";
  $("t-notas").classList.toggle("on", n === "notas"); $("t-chat").classList.toggle("on", n === "chat");
}
$("t-notas").onclick = () => aba("notas");
$("t-chat").onclick = () => { aba("chat"); $("cmsg").focus(); };
function bolha(papel, texto) {
  const d = document.createElement("div"); d.className = "b " + papel; d.textContent = texto;
  $("msgs").append(d); d.scrollIntoView({ block: "end" }); return d;
}
function proposta(p) {
  const d = document.createElement("div"); d.className = "b prop";
  const t = document.createElement("div"); t.textContent = p.descricao;
  const ok = document.createElement("button"); ok.className = "sec"; ok.textContent = "Confirmar";
  const no = document.createElement("button"); no.className = "sec"; no.textContent = "Cancelar";
  const fim = txt => d.replaceChildren(document.createTextNode(txt));
  ok.onclick = async () => { try { await api("/api/chat/confirmar", { id: p.id }); fim("✓ " + p.descricao); atualizar(); } catch { fim("Não foi possível aplicar (expirou ou já foi usada)."); } };
  no.onclick = async () => { try { await api("/api/chat/cancelar", { id: p.id }); } catch {} fim("✗ Cancelado: " + p.descricao); };
  d.append(t, ok, no); $("msgs").append(d); d.scrollIntoView({ block: "end" });
}
async function enviarChat() {
  const m = $("cmsg").value.trim(); if (!m) return;
  $("cmsg").value = ""; bolha("u", m);
  const esp = bolha("a", "…");
  try {
    const r = await api("/api/chat", { mensagem: m, historico: hist.slice(-6) });
    hist.push({ role: "user", content: m }, { role: "assistant", content: r.resposta });
    esp.textContent = r.resposta;
    r.propostas.forEach(proposta);
  } catch (e) { esp.textContent = String(e.message) === "503" ? "Modelo indisponível: o Ollama está ligado no PC?" : "Erro ao falar com o servidor."; }
}
$("cenviar").onclick = enviarChat;
$("cmsg").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarChat(); } });
