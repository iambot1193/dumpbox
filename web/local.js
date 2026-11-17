// Modo celular (GitHub Pages ou ?local=1): o app roda sem o PC. Responde às mesmas rotas /api/* que o servidor,
// guardando tudo no localStorage deste aparelho. Sem IA: cada nota vira um item "nota" na pasta Outro.
// Conectado ao PC (endereço em dumpbox.pc): as rotas vão para o PC com token Bearer, e as notas locais sobem uma vez.
// ponytail: só o que a tela usa; regras de prazo/prioridade copiadas de rules.py (manter as duas iguais).
(() => {
  const LOCAL = location.hostname.endsWith("github.io") || new URLSearchParams(location.search).has("local");
  if (!LOCAL) return;
  window.DUMPBOX_LOCAL = true;
  const K = "dumpbox.local";
  const PADRAO = [["casa", "Casa"], ["trabalho", "Trabalho"], ["freelance", "Freelance"], ["estudos", "Estudos"], ["saude", "Saúde"], ["financas", "Finanças"], ["outro", "Outro"]];
  const NIVEL = { critica: "crítica", alta: "alta", media: "média", baixa: "baixa" };
  let S;
  try { S = JSON.parse(localStorage.getItem(K)); } catch {}
  S ||= { seq: 1, itens: [], alt: [], pastas: PADRAO.map(([slug, nome]) => ({ slug, nome, descricao: "" })) };
  const salvar = () => localStorage.setItem(K, JSON.stringify(S));  // cheio: lança, a tela mostra "não consegui salvar"
  try { salvar(); } catch {}  // 1º uso: grava o estado inicial (o desfazer de erro relê daqui)

  const norm = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const p2 = n => String(n).padStart(2, "0");
  const iso = d => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
  const agora = () => { const d = new Date(); return new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 19); };
  const NUM = { um: 1, uma: 1, dois: 2, duas: 2, tres: 3, quatro: 4, cinco: 5, seis: 6, sete: 7, oito: 8, nove: 9, dez: 10, quinze: 15 };
  const DIAS3 = { dom: 0, seg: 1, ter: 2, qua: 3, qui: 4, sex: 5, sab: 6 };
  function prazo(texto) {  // mesmo comportamento de rules.resolver_prazo
    const t = norm(texto), d = new Date(); let ok = true, m;
    const soma = n => d.setDate(d.getDate() + n);
    if (t.includes("depois de amanha")) soma(2);
    else if (t.includes("amanha")) soma(1);
    else if (t.includes("hoje")) ;
    else if ((m = t.match(/(?:(?:daqui a|daqui|em)\s+(\w+)|\b(\d+))\s+(dia|semana|mes)/)) && (+(m[1] || m[2]) || NUM[m[1]])) soma((+(m[1] || m[2]) || NUM[m[1]]) * { dia: 1, semana: 7, mes: 30 }[m[3]]);
    else if ((m = t.match(/\bdia\s+(\d{1,2})\b/))) { const dia = +m[1]; if (dia < d.getDate()) d.setMonth(d.getMonth() + 1, 1); d.setDate(dia); ok = d.getDate() === dia; }
    else if ((m = t.match(/\b(seg|ter|qua|qui|sex|sab|dom)(?:unda|ca|rta|nta|ta|ado|ingo)?\b/))) soma((DIAS3[m[1]] - d.getDay() + 7) % 7 || 7);
    else if (t.includes("semana que vem")) soma(7);
    else ok = false;
    if (!ok) return null;
    const h = t.match(/\b(\d{1,2})(?::|h)(\d{2})?\b/);
    return h && +h[1] < 24 && +(h[2] || 0) < 60 ? `${iso(d)}T${p2(+h[1])}:${p2(+(h[2] || 0))}` : iso(d);
  }
  function prioridade(p, titulo) {
    if (norm(titulo).includes("urgente")) return "alta";
    if (!p) return "baixa";
    const [a, m, dd] = p.slice(0, 10).split("-").map(Number), h = new Date();
    const dias = Math.round((Date.UTC(a, m - 1, dd) - Date.UTC(h.getFullYear(), h.getMonth(), h.getDate())) / 864e5);
    return dias <= 1 ? "alta" : dias <= 7 ? "media" : "baixa";
  }
  const nomePasta = s => S.pastas.find(p => p.slug === s)?.nome || s;
  const slugDe = v => { const n = norm(v || "").trim(); return S.pastas.find(p => n && (norm(p.slug) === n || norm(p.nome) === n))?.slug; };
  const item = id => S.itens.find(i => i.id === +id);
  class Erro extends Error { constructor(st, detail) { super(st); this.st = st; this.detail = detail; } }

  function novoItem(titulo, extra) {
    const it = { id: S.seq++, tipo: "nota", titulo: titulo.slice(0, 200), contexto: "outro", prazo_em: null, prioridade: "baixa",
      estado: "catalogado", criado_em: agora(), grade_col: null, grade_lin: null, grade_larg: null, grade_alt: null, ...extra };
    S.itens.push(it); return it;
  }
  function valida(it, campo, valor) {  // devolve o valor final da coluna (como chat.validar)
    if (!it) throw new Erro(404, "item inexistente");
    if (campo === "prazo") { const p = prazo(valor || ""); if (!p) throw new Erro(422, `não entendi a data “${valor}”`); return ["prazo_em", p]; }
    if (campo === "contexto") { const s = slugDe(valor); if (!s) throw new Erro(422, "pasta inexistente"); return ["contexto", s]; }
    if (campo === "estado" && !["feito", "arquivado", "catalogado"].includes(valor)) throw new Erro(422, "estado inválido");
    if (campo === "prioridade" && !NIVEL[valor]) throw new Erro(422, "criticidade inválida");
    if (campo === "titulo" && !valor.trim()) throw new Erro(422, "título vazio");
    return [campo, campo === "titulo" ? valor.trim().slice(0, 200) : valor];
  }
  function frase(it, col, v) {
    const t = `“${it.titulo}”`;
    if (col === "estado") return `${t} ` + { feito: "marcado como feito", arquivado: "foi para a Lixeira", catalogado: "voltou para a pasta" }[v];
    if (col === "contexto") return `${t} foi para ${nomePasta(v)}`;
    if (col === "prioridade") return `${t} agora é ${NIVEL[v]}`;
    if (col === "prazo_em") return `Prazo de ${t}: ${v.replace("T", " ")}`;
    return `${t} editado`;
  }
  function aplica(grupo, pares) {  // pares: [item, coluna, valor]; grava o diário para o Desfazer
    let n = 0;
    for (const [it, col, v] of pares) {
      if (it[col] === v) continue;
      S.alt.push({ grupo, id: it.id, col, antes: it[col], depois: v, descricao: frase(it, col, v), desfeito: false });
      it[col] = v; n++;
    }
    S.alt = S.alt.slice(-300);
    return n;
  }

  const R = [  // [método, regex, função(corpo, ...grupos)]
    ["GET", /^estado$/, () => ({ configurado: true, preparo: { pronto: false, erro: null },
      aviso: "Modo celular: notas só neste aparelho, sem IA. Toque aqui para conectar ao PC." })],
    ["POST", /^(login|logout|setup)$/, () => ({ ok: true })],
    ["GET", /^sessao$/, () => ({ ok: true })],
    ["POST", /^capturas$/, b => {
      if (S.itens.some(i => i.captura_id === b.id)) return { nova: false };
      const linhas = b.texto.trim().split("\n");
      novoItem(linhas[0], { captura_id: b.id, texto: b.texto, criado_em: b.criado_em || agora() });
      return { nova: true };
    }],
    ["POST", /^capturas\/imagem$/, () => { throw new Erro(422, "Foto de lista só com o PC (a IA lê a imagem)."); }],
    ["GET", /^itens$/, () => ({
      itens: S.itens.filter(i => i.estado !== "arquivado").sort((a, b) => b.criado_em.localeCompare(a.criado_em) || b.id - a.id),
      revisar: [], lixeira: S.itens.filter(i => i.estado === "arquivado").sort((a, b) => b.id - a.id), pastas: S.pastas })],
    ["POST", /^itens$/, b => {
      const titulo = (b.titulo || "").trim(), pasta = slugDe(b.contexto), txt = (b.prazo || "").trim();
      if (!titulo) throw new Erro(422, "título vazio");
      if (!pasta) throw new Erro(422, "pasta inexistente");
      const p = txt ? prazo(txt) : null;
      if (txt && !p) throw new Erro(422, `não entendi a data “${txt}”. Tente “sexta 14h”, “amanhã” ou “dia 20”.`);
      const it = novoItem(titulo, { tipo: b.tipo, contexto: pasta, prazo_em: p, prioridade: b.prioridade || prioridade(p, titulo) });
      return { id: it.id, descricao: `“${it.titulo}” criado em ${nomePasta(pasta)}` };
    }],
    ["POST", /^itens\/editar$/, b => {
      const pares = [...new Set(b.ids)].map(id => { const it = item(id); return [it, ...valida(it, b.campo, b.valor)]; });
      const grupo = crypto.randomUUID(), n = aplica(grupo, pares);
      if (!n) return { grupo: null, descricao: null, n: 0 };
      const d = S.alt.filter(a => a.grupo === grupo);
      return { grupo, n, descricao: n === 1 ? d[0].descricao : `${n} itens alterados` };
    }],
    ["POST", /^itens\/(\d+)\/editar$/, (b, id) => {
      const it = item(id), pares = Object.entries(b.mudancas).map(([c, v]) => [it, ...valida(it, c, v)]);
      const grupo = crypto.randomUUID(), n = aplica(grupo, pares);
      return n ? { grupo, n, descricao: `“${it.titulo}” editado` } : { grupo: null, descricao: null, n: 0 };
    }],
    ["POST", /^itens\/(\d+)\/apagar$/, (b, id) => {
      if (item(id)?.estado !== "arquivado") throw new Erro(404, "item não está na Lixeira");
      S.itens = S.itens.filter(i => i.id !== +id); return { ok: true };
    }],
    ["POST", /^lixeira\/esvaziar$/, () => { const n = S.itens.length; S.itens = S.itens.filter(i => i.estado !== "arquivado"); return { apagados: n - S.itens.length }; }],
    ["POST", /^layout$/, b => { for (const p of b.itens) { const it = item(p.id); if (it) Object.assign(it, { grade_col: p.col, grade_lin: p.lin, grade_larg: p.larg, grade_alt: p.alt }); } return { ok: true }; }],
    ["POST", /^pastas$/, b => {
      const nome = b.nome.split(/\s+/).join(" ").trim().slice(0, 40), slug = norm(nome).replace(/[^a-z0-9 ]/g, "").trim().replace(/ +/g, "_");
      if (!slug) throw new Erro(422, "dê um nome com letras ou números");
      if (["hoje", "revisar", "lixeira"].includes(slug)) throw new Erro(422, `“${nome}” é o nome de uma tela do app; escolha outro`);
      if (slugDe(nome) || S.pastas.some(p => p.slug === slug)) throw new Erro(422, `já existe a pasta “${nome}”`);
      S.pastas.push({ slug, nome, descricao: b.descricao || "" });
      return { slug, nome };
    }],
    ["POST", /^pastas\/([^/]+)\/apagar$/, (b, s) => {
      const slug = decodeURIComponent(s);
      if (slug === "outro") throw new Erro(422, "a pasta Outro não pode ser apagada");
      if (!S.pastas.some(p => p.slug === slug)) throw new Erro(404, "pasta não existe");
      const lix = b.destino === "lixeira", destino = lix ? "outro" : slugDe(b.destino);
      if (!destino || destino === slug) throw new Erro(422, "escolha outra pasta para os itens");
      const nome = nomePasta(slug), grupo = crypto.randomUUID(), its = S.itens.filter(i => i.contexto === slug);
      aplica(grupo, its.flatMap(it => [...(lix ? [[it, "estado", "arquivado"]] : []), [it, "contexto", destino]]));
      S.pastas = S.pastas.filter(p => p.slug !== slug);
      return { movidos: its.length, grupo, descricao: `Pasta “${nome}” apagada` + (its.length ? `; ${its.length} item(ns) foram para ${lix ? "a Lixeira" : nomePasta(destino)}` : "") };
    }],
    ["GET", /^alteracoes$/, () => {
      const grupos = [...new Set(S.alt.map(a => a.grupo).reverse())].slice(0, 8);
      return grupos.map(g => { const l = S.alt.filter(a => a.grupo === g); return { grupo: g, descricoes: l.map(a => a.descricao), desfeito: l.every(a => a.desfeito) }; });
    }],
    ["POST", /^desfazer$/, b => {
      let n = 0;
      for (const a of S.alt.filter(a => a.grupo === b.grupo && !a.desfeito).reverse()) {
        const it = item(a.id);
        if (it && it[a.col] === a.depois) { it[a.col] = a.antes; n++; }
        a.desfeito = true;
      }
      return { revertidas: n };
    }],
  ];

  const fetchRede = window.fetch.bind(window);
  const rota = url => typeof url === "string" && url.match(/\/api\/(.+)$/)?.[1];
  const ler = k => { try { return localStorage.getItem(k); } catch { return null; } };
  const PC = ler("dumpbox.pc");

  if (PC) {  // ---- conectado: o PC é o servidor (IA, chat, foto); sem conexão, a fila de notas do app.js guarda ----
    let enviando = false;
    const comToken = op => { const t = ler("dumpbox.token"); return t ? { ...op, headers: { ...op.headers, Authorization: "Bearer " + t } } : op; };
    async function enviarLocais() {  // itens feitos no modo celular sobem uma vez; cópia fica em dumpbox.local.enviado
      const abertos = S.itens.filter(i => i.estado === "catalogado");
      if (enviando || !abertos.length) return;
      enviando = true;
      try { localStorage.setItem(K + ".enviado", JSON.stringify(S)); } catch {}
      let n = 0;
      for (const it of abertos) {
        const nota = it.captura_id && it.tipo === "nota" && it.contexto === "outro" && !it.prazo_em && it.titulo === it.texto.trim().split("\n")[0].slice(0, 200);
        const envia = (rota, corpo) => fetchRede(PC + "/api/" + rota, comToken({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) }));
        try {
          let r = nota ? await envia("capturas", { id: it.captura_id, texto: it.texto, criado_em: it.criado_em })  // intacta: a IA do PC classifica
            : await envia("itens", { titulo: it.titulo, contexto: nomePasta(it.contexto), tipo: it.tipo, prioridade: it.prioridade, prazo: it.prazo_em });
          if (r.status === 422 && !nota) r = await envia("itens", { titulo: it.titulo, contexto: "outro", tipo: it.tipo, prioridade: it.prioridade, prazo: it.prazo_em });
          if (!r.ok) break;
        } catch { break; }
        S.itens = S.itens.filter(i => i !== it); n++;
        try { salvar(); } catch {}
      }
      enviando = false;
      if (n) toast(`${n} ite${n > 1 ? "ns" : "m"} do modo celular enviado${n > 1 ? "s" : ""} ao PC`);
    }
    window.fetch = async (url, op = {}) => {
      const caminho = rota(url);
      if (!caminho) return fetchRede(url, op);
      const r = await fetchRede(PC + "/api/" + caminho, comToken(op));
      if (caminho === "login" && r.ok) { localStorage.setItem("dumpbox.token", (await r.clone().json()).token); enviarLocais(); }
      if (caminho === "sessao" && r.ok) enviarLocais();
      if (caminho === "logout") localStorage.removeItem("dumpbox.token");
      return r;
    };
    addEventListener("DOMContentLoaded", () => {
      const b = document.createElement("button");
      b.textContent = "Usar sem o PC (desconectar)"; b.className = "no";
      b.onclick = () => { localStorage.removeItem("dumpbox.pc"); localStorage.removeItem("dumpbox.token"); location.reload(); };
      document.getElementById("login").append(b);
    });
    return;
  }

  // ---- só no aparelho ----
  async function conectar() {
    let u = (prompt("Endereço do PC (o do Tailscale), ex.: https://meu-pc.tail1234.ts.net") || "").trim().replace(/\/+$/, "");
    if (!u) return;
    if (!/^https?:\/\//.test(u)) u = "https://" + u;
    try { if (!(await fetchRede(u + "/api/estado")).ok) throw 0; }
    catch { return toast("Não achei o dumpbox nesse endereço. O PC está ligado, com o Tailscale e o tailscale serve?"); }
    localStorage.setItem("dumpbox.pc", u); location.reload();  // recarrega já conectado: pede a senha do PC
  }
  window.fetch = async (url, op = {}) => {
    const caminho = rota(url);
    if (!caminho) return fetchRede(url, op);
    const metodo = op.method || "GET", corpo = op.body ? JSON.parse(op.body) : {};
    const json = (st, obj) => new Response(JSON.stringify(obj), { status: st, headers: { "Content-Type": "application/json" } });
    for (const [m, re, fn] of R) {
      const g = m === metodo && caminho.match(re);
      if (!g) continue;
      try { const r = fn(corpo, ...g.slice(1)); if (metodo === "POST") salvar(); return json(200, r); }
      catch (e) { try { S = JSON.parse(localStorage.getItem(K)) || S; } catch {}  // erro no meio: volta ao último salvo
        return json(e.st || 500, { detail: e.detail || "não consegui salvar neste aparelho" }); }
    }
    return json(404, { detail: "indisponível no modo celular" });
  };
  addEventListener("DOMContentLoaded", () => {
    for (const id of ["foto", "fab"]) document.getElementById(id).hidden = true;
    const p = document.getElementById("prep"); p.style.cursor = "pointer"; p.onclick = conectar;
  });
  // foto colada (Ctrl+V) travaria a fila: sem IA não há quem leia a imagem
  document.addEventListener("paste", e => {
    if ([...(e.clipboardData?.items || [])].some(i => i.kind === "file")) { e.stopImmediatePropagation(); e.preventDefault(); toast("Foto de lista só com o PC."); }
  }, true);
})();
