"""Contrato único: o modelo Pydantic gera o JSON Schema usado pelo Ollama/llama.cpp e pela validação."""
from typing import Literal

from pydantic import BaseModel, Field

Tipo = Literal["tarefa", "compromisso", "ideia", "compra", "nota"]
Contexto = Literal["casa", "trabalho", "freelance", "estudos", "saude", "financas", "outro"]


class ItemIA(BaseModel):
    """O que o modelo devolve. Data é só o trecho literal; o parser determinístico resolve."""
    tipo: Tipo
    titulo: str = Field(max_length=80)
    contexto: Contexto
    prazo_texto: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=5)


class SaidaIA(BaseModel):
    itens: list[ItemIA] = Field(min_length=1)


class Item(ItemIA):
    """Item final: ItemIA + campos derivados por regra."""
    prazo_em: str | None = None  # ISO 'YYYY-MM-DD' ou 'YYYY-MM-DDTHH:MM'
    prioridade: Literal["alta", "media", "baixa"] = "baixa"


if __name__ == "__main__":  # python -m dumpbox.schema > schema/saida_ia.schema.json
    import json

    print(json.dumps(SaidaIA.model_json_schema(), indent=2, ensure_ascii=False))
