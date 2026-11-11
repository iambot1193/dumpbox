"""Avalia o modelo de visão nos checklists sintéticos (gere antes com eval/gera_imagens.py).

uso: python eval/run_eval_visao.py [qwen2.5vl:3b] [-v]
Mede: imagens lidas, itens achados (recall), itens inventados, acerto de marcado/não marcado, latência p50.
Comparação de texto sem acento/caixa e com tolerância a 1-2 letras (difflib).
"""
import base64
import difflib
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from dumpbox import db, visao  # noqa: E402

DADOS = Path(__file__).resolve().parents[1] / "data" / "public"


def igual(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, db.normalizar(a), db.normalizar(b)).ratio() >= 0.85


def main(modelo: str) -> None:
    casos = [json.loads(l) for l in (DADOS / "imagens.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    lidas = achados = esperados = extras = marca_ok = 0
    lat, por_estilo = [], {}
    for c in casos:
        b64 = base64.b64encode((DADOS / c["imagem"]).read_bytes()).decode()
        t0 = time.perf_counter()
        try:
            linhas = visao.transcrever(b64, modelo)
        except RuntimeError as e:
            print(f"  FALHOU {c['imagem']}: {e}")
            continue
        finally:
            lat.append(time.perf_counter() - t0)
        lidas += 1
        esperados += len(c["linhas"])
        sobra = list(linhas)
        for exp in c["linhas"]:
            got = next((l for l in sobra if igual(l.texto, exp["texto"])), None)
            if got is None:
                if "-v" in sys.argv:
                    print(f"  NÃO ACHOU {c['imagem']}: {exp['texto']}")
                continue
            sobra.remove(got)
            achados += 1
            ok = got.marcado == exp["marcado"]
            marca_ok += ok
            e = por_estilo.setdefault(c["estilo"], [0, 0])
            e[0] += ok
            e[1] += 1
            if not ok and "-v" in sys.argv:
                print(f"  MARCA {c['imagem']} ({c['estilo']}): '{exp['texto']}' esperado={exp['marcado']}")
        extras += len(sobra)
    pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"  # noqa: E731
    print(f"modelo={modelo} imagens={len(casos)} lidas={pct(lidas, len(casos))}")
    print(f"itens_achados={pct(achados, esperados)} inventados={extras} marcado_certo={pct(marca_ok, achados)}")
    print("marcado por estilo: " + ", ".join(f"{k}={pct(a, b)}" for k, (a, b) in sorted(por_estilo.items())))
    print(f"latencia_s p50={statistics.median(lat):.1f} max={max(lat):.1f}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "-v"]
    main(args[0] if args else visao.MODELO)
