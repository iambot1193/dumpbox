"""Cria/troca a senha do app: python -m dumpbox.setup  (com PYTHONPATH=backend). Grava só o hash."""
import getpass
import secrets
import sys

from .auth import hash_senha
from .config import ARQ


def main() -> None:
    if sys.stdin.isatty():
        s1, s2 = getpass.getpass("Nova senha: "), getpass.getpass("Repita a senha: ")
    else:  # sem terminal (ex.: pipe): lê duas linhas
        s1, s2 = sys.stdin.readline().rstrip("\r\n"), sys.stdin.readline().rstrip("\r\n")
    if s1 != s2 or len(s1) < 8:
        sys.exit("Senhas diferentes ou com menos de 8 caracteres.")
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(
        f"DUMPBOX_PASSWORD_HASH={hash_senha(s1)}\nDUMPBOX_SECRET={secrets.token_hex(32)}\n", encoding="utf-8")
    print(f"Senha salva (hash) em {ARQ}. Reinicie o servidor.")


if __name__ == "__main__":
    main()
