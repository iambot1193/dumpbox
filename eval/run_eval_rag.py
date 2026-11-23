"""Avaliação da busca do chat (RAG) num banco inventado: recall@5 (item certo entre os 5 primeiros) e latência.
Com --chat também mede recusa ("não achei") e id inventado nas respostas do modelo.
Precisa do Ollama com o modelo de busca.MODELO (e qwen2.5 para --chat). Rodar: PYTHONUTF8=1 python eval/run_eval_rag.py [--chat]"""
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ["DUMPBOX_DB"] = str(Path(tempfile.mkdtemp()) / "rag.db")
from dumpbox import busca, chat, db  # noqa: E402

# (titulo, detalhe, pasta): 40 itens de mentira, com ruído parecido de propósito
ITENS = [
    ("Trocar óleo do carro", "Fiat, 10 mil km, oficina do Zé", "casa"), ("Calibrar pneus", None, "casa"),
    ("Renovar seguro do carro", "vence em dezembro, cotar 3 corretoras", "financas"), ("Lavar o carro", None, "casa"),
    ("Pagar IPVA", "parcela 3 de 3", "financas"), ("Consulta cardiologista", "levar exames de sangue", "saude"),
    ("Comprar whey", None, "saude"), ("Academia: treino de perna", "agachamento 4x10", "saude"),
    ("Marcar dentista", "limpeza semestral", "saude"), ("Exame de vista", "óculos riscado", "saude"),
    ("Reunião com gestor", "feedback do trimestre", "trabalho"), ("Relatório mensal de vendas", "BI do portal", "trabalho"),
    ("Corrigir bug do login", "token expira cedo", "trabalho"), ("Deploy da versão 2.3", None, "trabalho"),
    ("Proposta para cliente da padaria", "site com cardápio, R$ 1.500", "freelance"), ("Renovar domínio do cliente", "registro.br", "freelance"),
    ("Logo para a loja de roupas", "3 opções, paleta terrosa", "freelance"), ("Cobrar cliente atrasado", "nota fiscal de outubro", "freelance"),
    ("Estudar cálculo II", "integrais por partes", "estudos"), ("Entregar TCC capítulo 2", "orientador pediu referências", "estudos"),
    ("Ler artigo sobre RAG", "embeddings e busca híbrida", "estudos"), ("Prova de estatística", "distribuição normal", "estudos"),
    ("Comprar ração do gato", "Golden 10 kg", "casa"), ("Consertar torneira da cozinha", "vedante gasto", "casa"),
    ("Pagar conta de luz", None, "financas"), ("Investir no Tesouro Selic", "500 por mês", "financas"),
    ("Declarar imposto de renda", "recibos médicos na pasta azul", "financas"), ("Cancelar streaming que não uso", None, "financas"),
    ("Presente de aniversário da mãe", "ela quer um livro de receitas", "casa"), ("Viagem para a praia", "reservar pousada em janeiro", "outro"),
    ("Ideia: app de receitas por foto", None, "outro"), ("Aprender violão", "acordes básicos", "outro"),
    ("Arrumar o quarto", None, "casa"), ("Doar roupas velhas", "duas sacolas", "casa"),
    ("Backup do HD externo", "fotos de 2024", "outro"), ("Trocar senha do banco", None, "financas"),
    ("Vacina da gripe", "posto do bairro", "saude"), ("Configurar roteador novo", "senha do wifi na geladeira", "casa"),
    ("Comprar pilhas AA", None, "casa"), ("Curso de inglês: aula 5", "phrasal verbs", "estudos"),
]
# (pergunta, títulos que contam como acerto)
CASOS = [
    ("o que anotei sobre o carro?", {"Trocar óleo do carro", "Renovar seguro do carro", "Lavar o carro", "Calibrar pneus", "Pagar IPVA"}),
    ("quando é a manutenção do veículo?", {"Trocar óleo do carro", "Calibrar pneus"}),
    ("coisas de médico", {"Consulta cardiologista", "Marcar dentista", "Exame de vista", "Vacina da gripe"}),
    ("o que preciso fazer pelo coração?", {"Consulta cardiologista"}),
    ("cliente da padaria", {"Proposta para cliente da padaria"}),
    ("quanto vou cobrar pelo site?", {"Proposta para cliente da padaria"}),
    ("tem algo de nota fiscal?", {"Cobrar cliente atrasado"}),
    ("faculdade", {"Estudar cálculo II", "Entregar TCC capítulo 2", "Prova de estatística"}),
    ("trabalho de conclusão", {"Entregar TCC capítulo 2"}),
    ("o que anotei do gato?", {"Comprar ração do gato"}),
    ("vazamento na pia", {"Consertar torneira da cozinha"}),
    ("impostos", {"Declarar imposto de renda", "Pagar IPVA"}),
    ("onde estão os recibos médicos?", {"Declarar imposto de renda"}),
    ("aniversário da minha mãe", {"Presente de aniversário da mãe"}),
    ("férias", {"Viagem para a praia"}),
    ("senha do wifi", {"Configurar roteador novo"}),
    ("fotos antigas", {"Backup do HD externo"}),
    ("investimentos", {"Investir no Tesouro Selic"}),
    ("problema no login", {"Corrigir bug do login"}),
    ("musculação", {"Academia: treino de perna", "Comprar whey"}),
    ("inglês", {"Curso de inglês: aula 5"}),
    ("logo", {"Logo para a loja de roupas"}),
]
SEM_RESPOSTA = ["o que anotei sobre o casamento do Pedro?", "tem algo sobre a mudança para Portugal?", "qual a senha do Netflix?"]


def main() -> None:
    c = db.conectar()
    for k, (t, d, p) in enumerate(ITENS):
        db.nova_captura(c, f"c{k}", t)
        c.execute("INSERT INTO item(captura_id,tipo,titulo,contexto,prioridade,estado,criado_em,detalhe) VALUES(?,'tarefa',?,?,'media','catalogado',?,?)",
                  (f"c{k}", t, p, db.agora(), d))
    c.commit()
    t0 = time.time()
    busca.indexar(c)
    print(f"indexou {len(ITENS)} itens em {time.time() - t0:.1f}s ({busca.MODELO})")
    titulo = {r["id"]: r["titulo"] for r in c.execute("SELECT id, titulo FROM item")}
    acertos, lat = 0, []
    for q, certos in CASOS:
        t0 = time.time()
        top = [titulo[i] for i in busca.buscar(c, q, 5)]
        lat.append(time.time() - t0)
        ok = bool(certos & set(top))
        acertos += ok
        if not ok:
            print(f"  ERROU {q!r}: {top}")
    lat.sort()
    print(f"recall@5: {acertos}/{len(CASOS)} = {acertos / len(CASOS):.0%} · busca p50 {lat[len(lat) // 2] * 1000:.0f} ms")

    if "--chat" in sys.argv:
        recusas, inventados, lat = 0, 0, []
        for q in SEM_RESPOSTA + [q for q, _ in CASOS[:6]]:
            t0 = time.time()
            r = chat.conversar(c, q, [])["resposta"]
            lat.append(time.time() - t0)
            inventados += sum(int(i) not in titulo for i in re.findall(r"#(\d+)", r))
            if q in SEM_RESPOSTA:
                recusas += "não achei" in r.lower()
            print(f"  {q!r} -> {r[:110]!r}")
        lat.sort()
        print(f"recusa correta: {recusas}/{len(SEM_RESPOSTA)} · ids inventados: {inventados} · chat p50 {lat[len(lat) // 2]:.1f}s")


if __name__ == "__main__":
    main()
