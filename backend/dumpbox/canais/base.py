"""Núcleo dos bots (Telegram hoje, WhatsApp depois): só traduz mensagem em captura, chat ou comando.
Nenhuma regra própria: captura passa pelo worker, pedido à IA passa por chat.conversar (validar, só item citado, reversível)."""
from collections import defaultdict, deque
from time import monotonic

from .. import chat, db, lembretes

AJUDA = ("Mande qualquer texto: vira nota e a IA cataloga.\n"
         "? pedido: fala com a IA (ex.: ? passa o dentista pra sexta)\n"
         "/hoje: atrasados e de hoje · /desfazer: volta o último pedido à IA")
LIMITE = 20  # mensagens por minuto por remetente
_historico: dict[str, list] = defaultdict(list)
_grupos: dict[str, list] = defaultdict(list)
_vistas: dict[str, deque] = defaultdict(deque)


def id_captura(canal: str, remetente: str, msg_id: str) -> str:
    return f"{ {'telegram': 'tg', 'whatsapp': 'zap'}.get(canal, canal)}-{remetente}-{msg_id}"


def criados(c, captura_id: str) -> str | None:
    """Depois que o worker classificou: o que virou a nota (None = ainda pendente)."""
    st = c.execute("SELECT status FROM captura WHERE id=?", (captura_id,)).fetchone()
    if not st or st["status"] == "pendente":
        return None
    its = c.execute("SELECT titulo, contexto, prazo_em FROM item WHERE captura_id=?", (captura_id,)).fetchall()
    if not its:
        return "A IA não achou item nessa nota (veja em Revisar)."
    return "\n".join(f"• {i['titulo']} · {db.nome_pasta(i['contexto'])}" + (f" · {i['prazo_em'].replace('T', ' ')}" if i["prazo_em"] else "")
                     for i in its)


def excedeu(remetente: str, agora: float | None = None) -> bool:
    agora = monotonic() if agora is None else agora
    v = _vistas[remetente]
    while v and agora - v[0] > 60:
        v.popleft()
    v.append(agora)
    return len(v) > LIMITE


def tratar(c, canal: str, remetente: str, msg_id: str, texto: str, conversar=chat.conversar) -> str | None:
    """Devolve a resposta (None = não responder). Quem chama já conferiu que o remetente é permitido."""
    texto = (texto or "").strip()
    chave = f"{canal}:{remetente}"
    if not texto or excedeu(chave):
        return None
    cmd = texto.split()[0].split("@")[0].lower()
    if cmd in ("/start", "/ajuda", "/help"):
        return AJUDA
    if cmd == "/hoje":
        return lembretes.resumo(c)
    if cmd == "/desfazer":
        if not _grupos[chave]:
            return "Nada para desfazer."
        n = chat.desfazer(c, _grupos[chave].pop())
        return f"Desfeito ({n} alteração(ões))."
    if texto.startswith("?"):
        pedido, h = texto[1:].strip(), _historico[chave]
        try:
            r = conversar(c, pedido, h)
        except RuntimeError:
            return "A IA não respondeu agora (o PC está preparando o modelo?). Tente de novo."
        h += [{"role": "user", "content": pedido}, {"role": "assistant", "content": r["resposta"]}]
        del h[:-12]
        if r.get("grupo"):
            _grupos[chave].append(r["grupo"])
        return r["resposta"] + ("".join(f"\n✓ {f}" for f in r["feitas"]) if r["feitas"] else "")
    nova = db.nova_captura(c, id_captura(canal, remetente, msg_id), texto, origem=canal)
    return "anotado ✓" if nova else None  # repetida (reenvio): não duplica nem responde de novo
