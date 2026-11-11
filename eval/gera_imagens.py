"""Gera checklists sintéticos (PNG) + gabarito para avaliar o modelo de visão.

uso: python eval/gera_imagens.py   -> data/public/imagens/*.png e data/public/imagens.jsonl
Varia fonte, inclinação, ruído e forma de marcar (caixa com ✓, X, texto riscado). Nada de dado real.
"""
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parents[1]
OUT = RAIZ / "data" / "public" / "imagens"
LISTAS = [
    ("Mercado", ["Arroz", "Feijão", "Café", "Leite", "Detergente", "Papel toalha"]),
    ("Semana", ["Pagar conta de luz", "Levar carro na oficina", "Ligar pro dentista", "Enviar relatório"]),
    ("Faculdade", ["Ler capítulo 4", "Lista de exercícios de cálculo", "Entregar resumo de redes", "Estudar SQL"]),
    ("Casa", ["Trocar lâmpada da cozinha", "Limpar caixa d'água", "Consertar torneira", "Regar plantas", "Lavar cortinas"]),
    ("Trabalho", ["Revisar pull request", "Reunião com o time", "Atualizar planilha de horas"]),
    ("Viagem", ["Comprar passagem", "Reservar hotel", "Separar documentos", "Trocar dinheiro", "Fazer mala"]),
    ("Freela", ["Mandar orçamento", "Ajustar logo", "Renovar domínio", "Emitir nota fiscal"]),
    ("Saúde", ["Marcar exame de sangue", "Comprar vitamina D", "Agendar fisioterapia"]),
    ("Festa", ["Comprar bolo", "Convidar amigos", "Alugar mesas", "Comprar refrigerante", "Decorar sala", "Pedir salgados"]),
    ("Mudança", ["Encaixotar livros", "Desligar internet", "Contratar frete", "Pintar quarto"]),
    ("Estudos", ["Revisar flashcards", "Assistir aula gravada", "Fazer simulado"]),
    ("Pendências", ["Declarar imposto", "Cancelar streaming", "Pagar IPVA", "Renovar CNH"]),
]
FONTES = ["arial.ttf", "calibri.ttf", "georgia.ttf", "segoeui.ttf", "comic.ttf", "consola.ttf"]


def fonte(nome: str, tam: int):
    try:
        return ImageFont.truetype(nome, tam)
    except OSError:
        return ImageFont.load_default(tam)


def desenhar(titulo: str, itens: list[str], marcados: set[int], estilo: str, rnd: random.Random) -> Image.Image:
    f, tam = rnd.choice(FONTES), rnd.randint(28, 40)
    ft, fi = fonte(f, tam + 10), fonte(f, tam)
    alt = 140 + len(itens) * int(tam * 1.9)
    img = Image.new("RGB", (900, alt), rnd.choice([(255, 255, 255), (252, 249, 238), (245, 247, 250)]))
    d = ImageDraw.Draw(img)
    d.text((60, 40), titulo, fill=(20, 20, 20), font=ft)
    y = 40 + tam * 2.4
    for n, txt in enumerate(itens):
        x, cx = 60, 60
        marcado = n in marcados
        if estilo != "riscado":  # caixa de seleção
            s = int(tam * 0.9)
            d.rectangle([cx, y + 4, cx + s, y + 4 + s], outline=(30, 30, 30), width=3)
            if marcado and estilo == "check":
                d.line([(cx + 5, y + 4 + s * .55), (cx + s * .4, y + s), (cx + s + 4, y - 2)], fill=(20, 90, 200), width=5)
            elif marcado:
                d.line([(cx + 4, y + 8), (cx + s - 4, y + s)], fill=(200, 30, 30), width=4)
                d.line([(cx + s - 4, y + 8), (cx + 4, y + s)], fill=(200, 30, 30), width=4)
            x = cx + s + 22
        d.text((x, y), txt, fill=(25, 25, 25), font=fi)
        if marcado and estilo == "riscado":
            w = d.textlength(txt, font=fi)
            d.line([(x - 4, y + tam * .6), (x + w + 4, y + tam * .6)], fill=(25, 25, 25), width=4)
        y += tam * 1.9
    img = img.rotate(rnd.uniform(-3, 3), expand=True, fillcolor=(200, 200, 200))
    return img.filter(ImageFilter.GaussianBlur(rnd.choice([0, 0, 0.6, 1.0])))


def main() -> None:
    rnd = random.Random(42)
    OUT.mkdir(parents=True, exist_ok=True)
    casos = []
    for n, (titulo, itens) in enumerate(LISTAS * 2):  # 24 imagens: cada lista em dois estilos
        estilo = ["check", "x", "riscado"][n % 3]
        marcados = set(rnd.sample(range(len(itens)), rnd.randint(1, len(itens) // 2)))
        nome = f"lista_{n:02d}.png"
        desenhar(titulo, itens, marcados, estilo, rnd).save(OUT / nome)
        casos.append({"imagem": f"imagens/{nome}", "estilo": estilo,
                      "linhas": [{"texto": t, "marcado": i in marcados} for i, t in enumerate(itens)]})
    (OUT.parent / "imagens.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in casos), encoding="utf-8")
    print(len(casos), "imagens em", OUT)


if __name__ == "__main__":
    main()
