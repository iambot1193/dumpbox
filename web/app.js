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
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
function mostra(tela) { $("login").hidden = tela !== "login"; $("app").hidden = tela !== "app"; }

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

async function iniciar() {
  // 401 -> api() já mostrou o login; offline -> segue no app (a fila local guarda as notas)
  try { await api("/api/sessao"); } catch (e) { if (String(e.message) === "401") return; }
  mostra("app"); await enviarFila(); atualizar();
}
window.addEventListener("online", () => { enviarFila().then(atualizar); });
setInterval(() => { if (!$("app").hidden) { enviarFila(); atualizar(); } }, 5000);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
iniciar();
