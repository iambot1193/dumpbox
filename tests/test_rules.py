import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from dumpbox.rules import prioridade, resolver_prazo  # noqa: E402

AGORA = datetime(2026, 11, 10, 9, 0)  # terça

CASOS = {
    "amanhã": "2026-11-11",
    "hoje 16:30": "2026-11-10T16:30",
    "depois de amanhã": "2026-11-12",
    "sexta às 14h": "2026-11-13T14:00",
    "terça": "2026-11-17",  # mesmo dia da semana = próxima
    "segunda": "2026-11-16",
    "dia 15": "2026-11-15",
    "dia 5": "2026-12-05",  # já passou: mês que vem
    "daqui 3 dias": "2026-11-13",
    "em 2 semanas": "2026-11-24",
    "semana que vem": "2026-11-17",
    "2 semanas": "2026-11-24",  # modelo costuma copiar sem o 'em'
    "3 dias": "2026-11-13",
    "daqui a três dias": "2026-11-13",
    "pagar boleto dia 20": "2026-11-20",  # 'boleto dia' não pode virar relativo
    "sex": "2026-11-13",  # abreviação de WhatsApp
    "até qua": "2026-11-11",
    "sábado": "2026-11-14",
    "sexta-feira": "2026-11-13",
    "terça 10h": "2026-11-17T10:00",
    "um dia qualquer": None,
    None: None,
}


def test_resolver_prazo():
    for texto, esperado in CASOS.items():
        assert resolver_prazo(texto, AGORA) == esperado, texto


def test_prioridade():
    assert prioridade("2026-11-11", "x", AGORA) == "alta"
    assert prioridade("2026-11-15", "x", AGORA) == "media"
    assert prioridade("2026-12-30", "x", AGORA) == "baixa"
    assert prioridade(None, "x", AGORA) == "baixa"
    assert prioridade(None, "Pagar URGENTE", AGORA) == "alta"


if __name__ == "__main__":
    test_resolver_prazo()
    test_prioridade()
    print("ok")
