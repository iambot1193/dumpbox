"""Garante Ollama + modelo no PC do usuário na primeira execução. Estado lido pela UI (barra de progresso)."""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile

import httpx

from . import config
from .classifier import OLLAMA_URL

ZIP_URL = "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"
DIR = config.HOME / "ollama"
ESTADO = {"fase": "inicio", "pct": 0, "msg": "", "erro": None, "modelo": None, "pronto": False}


def ram_gb() -> float:
    if sys.platform == "win32":
        class MS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong),
                        ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong), ("f", ctypes.c_ulonglong)]
        ms = MS(); ms.l = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return ms.total / 2**30
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30


def escolher_modelo() -> str:
    """7B precisa de ~6 GB livres de RAM; abaixo de 16 GB totais cai para o 1.5B (bem menos preciso)."""
    return os.getenv("DUMPBOX_MODEL") or ("qwen2.5:7b" if ram_gb() >= 15 else "qwen2.5:1.5b")


def modelo() -> str:
    return ESTADO["modelo"] or escolher_modelo()


def pronto() -> bool:
    """Sem DUMPBOX_AUTOPREPARO (dev/testes) assume que o Ollama já está de pé."""
    return ESTADO["pronto"] or os.getenv("DUMPBOX_AUTOPREPARO") != "1"


def _set(fase: str, pct: int = 0, msg: str = "") -> None:
    ESTADO.update(fase=fase, pct=pct, msg=msg)


def _online() -> bool:
    try:
        return httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def _exe() -> str | None:
    local = DIR / "ollama.exe"
    return str(local) if local.exists() else shutil.which("ollama")


def _baixar_ollama() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Instale o Ollama (ollama.com) e reabra o dumpbox.")
    livre = shutil.disk_usage(config.HOME.anchor or ".").free / 2**30
    if livre < 10:
        raise RuntimeError(f"Pouco espaço em disco ({livre:.0f} GB livres). Libere ~10 GB.")
    DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DIR / "ollama.zip.part"
    with httpx.stream("GET", ZIP_URL, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        total, feito = int(r.headers.get("content-length", 0)), 0
        with open(zip_path, "wb") as f:
            for bloco in r.iter_bytes(1 << 20):
                f.write(bloco)
                feito += len(bloco)
                _set("baixando_ollama", int(100 * feito / total) if total else 0, "Baixando o Ollama (motor da IA)")
    _set("extraindo", 100, "Extraindo o Ollama")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(DIR)
    zip_path.unlink()


def _subir(exe: str) -> None:
    env = {**os.environ, "OLLAMA_MODELS": str(DIR / "models")}
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen([exe, "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    for _ in range(60):
        if _online():
            return
        time.sleep(1)
    raise RuntimeError("O Ollama não respondeu em 60 s.")


def _garantir_modelo(nome: str, progresso: bool = True) -> None:
    tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10).json().get("models", [])
    if any(m["name"] == nome or m["name"].startswith(nome + ":") for m in tags):
        return
    with httpx.stream("POST", f"{OLLAMA_URL}/api/pull", json={"model": nome, "stream": True}, timeout=None) as r:
        r.raise_for_status()
        for linha in r.iter_lines():
            if not linha:
                continue
            d = json.loads(linha)
            if d.get("error"):
                raise RuntimeError(d["error"])
            if progresso and d.get("total"):
                _set("baixando_modelo", int(100 * d.get("completed", 0) / d["total"]), f"Baixando o modelo {nome}")


def preparar() -> None:
    """Ollama já rodando? usa. Senão: acha/baixa, sobe, e garante o modelo. Erros ficam em ESTADO['erro']."""
    try:
        ESTADO.update(erro=None, modelo=escolher_modelo())
        if not _online():
            if not _exe():
                _baixar_ollama()
            _set("iniciando", 100, "Iniciando o Ollama")
            _subir(_exe())
        _garantir_modelo(ESTADO["modelo"])
        _set("pronto", 100, "Pronto")
        ESTADO["pronto"] = True
        from .visao import MODELO as VISAO
        _garantir_modelo(VISAO, progresso=False)  # depois do texto e sem barra: só fotos esperam por ele
    except Exception as e:  # mostra na UI em vez de morrer calado
        ESTADO["erro"] = str(e)[:300]


def iniciar_em_thread() -> None:
    threading.Thread(target=preparar, daemon=True).start()
