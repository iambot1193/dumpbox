"""Harness: roda um modelo sobre os casos e imprime métricas por campo.

uso: python eval/run_eval.py qwen2.5:1.5b [data/public/casos.jsonl]
Itens são comparados por ordem; se o nº de itens difere, só conta no acerto de split.
"""
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from dumpbox.classifier import classificar  # noqa: E402


def main(modelo: str, arq: str) -> None:
    casos = [json.loads(l) for l in Path(arq).read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(casos)
    valido = split = 0
    campos = {"tipo": [0, 0], "contexto": [0, 0], "prazo_em": [0, 0]}
    lat = []
    for c in casos:
        r = classificar(c["texto"], datetime.fromisoformat(c["agora"]), modelo)
        lat.append(r.latencia_ms)
        if r.itens is None:
            continue
        valido += 1
        if len(r.itens) != len(c["esperado"]):
            continue
        split += 1
        for got, exp in zip(r.itens, c["esperado"]):
            for k in campos:
                campos[k][1] += 1
                ok = getattr(got, k) == exp[k]
                campos[k][0] += ok
                if not ok and "-v" in sys.argv:
                    print(f"  ERRO {k}: '{c['texto']}' esperado={exp[k]} obtido={getattr(got, k)}")
    pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"  # noqa: E731
    from dumpbox.classifier import PROMPT_V
    print(f"modelo={modelo} prompt={PROMPT_V} casos={n}")
    print(f"json_valido={pct(valido, n)} split_correto={pct(split, n)}")
    for k, (a, b) in campos.items():
        print(f"{k}={pct(a, b)}")
    print(f"latencia_ms p50={statistics.median(lat):.0f} max={max(lat)}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "-v"]
    main(args[0], args[1] if len(args) > 1 else "data/public/casos.jsonl")
