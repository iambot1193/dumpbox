"""Pasta de dados e config.env. Dev: data/private/. Exe (PyInstaller): %LOCALAPPDATA%/dumpbox. Override: DUMPBOX_HOME."""
import os
import sys
from pathlib import Path

if os.getenv("DUMPBOX_HOME"):
    HOME = Path(os.environ["DUMPBOX_HOME"])
elif getattr(sys, "frozen", False):
    HOME = Path(os.getenv("LOCALAPPDATA", Path.home())) / "dumpbox"
else:
    HOME = Path(__file__).resolve().parents[2] / "data" / "private"

ARQ = Path(os.getenv("DUMPBOX_CONFIG", HOME / "config.env"))


def carregar() -> None:
    if not ARQ.exists():
        return
    for linha in ARQ.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


carregar()
