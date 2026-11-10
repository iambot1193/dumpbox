"""Cria/troca a senha do app. CLI: python -m dumpbox.setup (PYTHONPATH=backend). A API usa salvar_senha()."""
import getpass
import os
import secrets
import sys

from . import auth
from .config import ARQ


def salvar_senha(senha: str) -> None:
    """Grava só o hash + segredo de sessão e já ativa no processo (sem reiniciar)."""
    if len(senha) < 8:
        raise ValueError("a senha precisa ter pelo menos 8 caracteres")
    h, segredo = auth.hash_senha(senha), secrets.token_hex(32)
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(f"DUMPBOX_PASSWORD_HASH={h}\nDUMPBOX_SECRET={segredo}\n", encoding="utf-8")
    os.environ["DUMPBOX_PASSWORD_HASH"] = h
    auth.trocar_segredo(segredo)


def main() -> None:
    if sys.stdin.isatty():
        s1, s2 = getpass.getpass("Nova senha: "), getpass.getpass("Repita a senha: ")
    else:  # sem terminal (ex.: pipe): lê duas linhas
        s1, s2 = sys.stdin.readline().rstrip("\r\n"), sys.stdin.readline().rstrip("\r\n")
    if s1 != s2:
        sys.exit("Senhas diferentes.")
    try:
        salvar_senha(s1)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Senha salva (hash) em {ARQ}. Reinicie o servidor.")


if __name__ == "__main__":
    main()
