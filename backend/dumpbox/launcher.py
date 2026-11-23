"""Entrada do .exe: sobe o servidor local e abre o navegador. Fechar a janela encerra o dumpbox."""
import os
import socket
import subprocess
import threading
import webbrowser


def _porta_livre(preferida: int = 8000) -> int:
    for p in range(preferida, preferida + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return preferida


def _abrir(url: str) -> None:
    """Janela própria (Edge --app: sem barra de endereço, ícone na barra de tarefas); sem Edge, o navegador padrão."""
    for base in (os.getenv("ProgramFiles(x86)"), os.getenv("ProgramFiles")):
        edge = base and os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
        if edge and os.path.exists(edge):
            subprocess.Popen([edge, f"--app={url}"])
            return
    webbrowser.open(url)


def main() -> None:
    os.environ.setdefault("DUMPBOX_AUTOPREPARO", "1")  # baixa/inicia Ollama + modelo na 1ª execução
    import uvicorn

    from dumpbox.api import app

    porta = _porta_livre()
    url = f"http://127.0.0.1:{porta}"
    print(f"dumpbox rodando em {url}\nDeixe esta janela aberta enquanto usa o app. Feche para encerrar.")
    if os.getenv("DUMPBOX_NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: _abrir(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")
