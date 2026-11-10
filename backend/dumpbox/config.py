"""Carrega data/private/config.env (gitignored) para o ambiente, sem sobrescrever variáveis já definidas."""
import os
from pathlib import Path

ARQ = Path(os.getenv("DUMPBOX_CONFIG", Path(__file__).resolve().parents[2] / "data" / "private" / "config.env"))


def carregar() -> None:
    if not ARQ.exists():
        return
    for linha in ARQ.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


carregar()
