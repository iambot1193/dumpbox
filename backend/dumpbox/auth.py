"""Senha própria do app (NÃO a do Windows). scrypt da stdlib + cookie de sessão assinado."""
import hashlib
import hmac
import os
import secrets
import sys
import time

SESSAO_S = 7 * 24 * 3600
_SEGREDO = os.getenv("DUMPBOX_SECRET") or secrets.token_hex(32)  # sem env: sessões morrem ao reiniciar
_tentativas: dict[str, list[float]] = {}


def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=2**14, r=8, p=1)
    return f"{sal.hex()}${h.hex()}"


def confere_senha(senha: str, guardado: str | None) -> bool:
    if not guardado or "$" not in guardado:
        return False
    sal, h = guardado.split("$", 1)
    novo = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=2**14, r=8, p=1)
    return hmac.compare_digest(novo.hex(), h)


def limite_ok(ip: str, max_tent: int = 5, janela: int = 60) -> bool:
    """Brute-force: no máx. 5 tentativas/min por IP. ponytail: em memória, vale p/ 1 processo."""
    agora = time.time()
    ts = [t for t in _tentativas.get(ip, []) if agora - t < janela]
    ts.append(agora)
    _tentativas[ip] = ts
    return len(ts) <= max_tent


def _assina(exp: str) -> str:
    return hmac.new(_SEGREDO.encode(), exp.encode(), hashlib.sha256).hexdigest()


def novo_token() -> str:
    exp = str(int(time.time()) + SESSAO_S)
    return f"{exp}.{_assina(exp)}"


def token_valido(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    return exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, _assina(exp))


if __name__ == "__main__":  # python -m dumpbox.auth 'minha senha'  -> valor p/ DUMPBOX_PASSWORD_HASH
    print(hash_senha(sys.argv[1]))
