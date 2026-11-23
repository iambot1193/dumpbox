"""Lembretes pelo bot: item com prazo e `lembrete` (minutos antes) avisa uma vez, mesmo com a PWA fechada.
Mesma regra da tela (app.js alvoLembrete): prazo só com dia = 9h. PC desligado: avisa ao ligar, marcado "atrasado"."""
from datetime import datetime, timedelta

from . import db


def alvo(prazo_em: str, lembrete: int) -> datetime:
    return datetime.fromisoformat(prazo_em if len(prazo_em) > 10 else prazo_em + "T09:00") - timedelta(minutes=lembrete)


def pendentes(c, agora: datetime) -> list:
    rows = c.execute("SELECT id, titulo, prazo_em, lembrete FROM item WHERE estado='catalogado' AND prazo_em IS NOT NULL "
                     "AND lembrete IS NOT NULL AND avisado_em IS NULL").fetchall()
    return [r for r in rows if alvo(r["prazo_em"], r["lembrete"]) <= agora]


def avisar(c, enviar, agora: datetime | None = None) -> int:
    """Envia cada lembrete vencido e marca avisado_em. Envio falhou: fica pendente para o próximo minuto."""
    agora = agora or datetime.now()
    n = 0
    for r in pendentes(c, agora):
        quando = r["prazo_em"].replace("T", " ")
        atraso = "atrasado: " if datetime.fromisoformat(r["prazo_em"] if len(r["prazo_em"]) > 10 else r["prazo_em"] + "T23:59") < agora else ""
        try:
            enviar(f"🔔 {atraso}{r['titulo']} ({quando})")
        except Exception:
            continue
        c.execute("UPDATE item SET avisado_em=? WHERE id=?", (db.agora(), r["id"]))
        c.commit()
        n += 1
    return n


def resumo(c, agora: datetime | None = None) -> str:
    """Atrasados + hoje (usado pelo /hoje e pelo resumo diário)."""
    hoje = (agora or datetime.now()).strftime("%Y-%m-%d")
    rows = c.execute("SELECT titulo, prazo_em FROM item WHERE estado='catalogado' AND prazo_em IS NOT NULL "
                     "AND substr(prazo_em,1,10) <= ? ORDER BY prazo_em", (hoje,)).fetchall()
    if not rows:
        return "Hoje: nada com prazo."
    return "Hoje:\n" + "\n".join(("⚠ " if r["prazo_em"][:10] < hoje else "• ") + r["titulo"] for r in rows)
