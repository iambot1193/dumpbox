"""QR "Conectar celular": descobre o endereço Tailscale deste PC e liga o `tailscale serve` na porta do app se faltar."""
import json
import re
import shutil
import subprocess

EXE = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"


def _ts(*args, timeout=10) -> str:
    return subprocess.run([EXE, *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout


def endereco(porta: int) -> dict:
    """{"url": "https://pc.tailXXXX.ts.net"} ou {"erro": "...", "link": opcional}."""
    try:
        st = json.loads(_ts("status", "--json"))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"erro": "Tailscale não instalado neste PC", "link": "https://tailscale.com/download"}
    if st.get("BackendState") != "Running":
        return {"erro": "Tailscale desligado ou sem login neste PC. Abra o Tailscale e entre na sua conta."}
    url = "https://" + st["Self"]["DNSName"].rstrip(".")
    try:
        if f"127.0.0.1:{porta}" not in _ts("serve", "status", "--json"):
            _ts("serve", "--bg", str(porta), timeout=20)
    except subprocess.TimeoutExpired as e:  # 1ª vez na conta: o serve espera ativar o HTTPS no painel
        saida = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        link = re.search(r"https://login\.tailscale\.com/\S+", saida)
        return {"erro": "Ative o HTTPS da sua rede Tailscale (1 vez) e tente de novo.", "link": link and link.group(0)}
    return {"url": url}
