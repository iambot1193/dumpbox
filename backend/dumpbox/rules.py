"""Regras determinísticas pt-BR: resolvem datas relativas e prioridade. Sem IA, sem dependência."""
import re
import unicodedata
from datetime import date, datetime, timedelta

_DIAS3 = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6}
_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
        "sete": 7, "oito": 8, "nove": 9, "dez": 10, "quinze": 15}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _relativo(t: str) -> int | None:
    """'em 2 semanas', 'daqui a três dias', '3 dias' -> nº de dias. O prefixo é opcional só com dígitos."""
    m = re.search(r"(?:(?:daqui a|daqui|em)\s+(\w+)|\b(\d+))\s+(dia|semana|mes)", t)
    if not m:
        return None
    g = m[1] or m[2]
    n = int(g) if g.isdigit() else _NUM.get(g)
    return None if not n else n * {"dia": 1, "semana": 7, "mes": 30}[m[3]]


def _hora(t: str) -> str | None:
    m = re.search(r"\b(\d{1,2})(?::|h)(\d{2})?\b", t)
    if not m:
        return None
    h, mi = int(m[1]), int(m[2] or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def resolver_prazo(texto: str | None, agora: datetime) -> str | None:
    """'amanhã 10h' -> '2026-11-11T10:00'. None se não entender (cai na aba revisar)."""
    if not texto:
        return None
    t = _norm(texto)
    hoje = agora.date()
    d: date | None = None

    if "depois de amanha" in t:
        d = hoje + timedelta(days=2)
    elif "amanha" in t:
        d = hoje + timedelta(days=1)
    elif "hoje" in t:
        d = hoje
    elif (dias := _relativo(t)) is not None:
        d = hoje + timedelta(days=dias)
    elif m := re.search(r"\bdia\s+(\d{1,2})\b", t):
        dia = int(m[1])
        try:
            d = hoje.replace(day=dia) if dia >= hoje.day else (hoje.replace(day=1) + timedelta(days=32)).replace(day=dia)
        except ValueError:
            d = None
    elif m := re.search(r"\b(seg|ter|qua|qui|sex|sab|dom)(?:unda|ca|rta|nta|ta|ado|ingo)?\b", t):  # "sex" = sexta
        delta = (_DIAS3[m[1]] - hoje.weekday()) % 7 or 7  # sempre a próxima ocorrência
        d = hoje + timedelta(days=delta)
    elif "semana que vem" in t:
        d = hoje + timedelta(days=7)

    if d is None:
        return None
    h = _hora(t)
    return f"{d.isoformat()}T{h}" if h else d.isoformat()


def prioridade(prazo_em: str | None, titulo: str, agora: datetime) -> str:
    """alta: prazo <=1 dia ou 'urgente'; media: <=7 dias; baixa: resto."""
    if "urgente" in _norm(titulo):
        return "alta"
    if not prazo_em:
        return "baixa"
    dias = (datetime.fromisoformat(prazo_em).date() - agora.date()).days
    return "alta" if dias <= 1 else "media" if dias <= 7 else "baixa"
