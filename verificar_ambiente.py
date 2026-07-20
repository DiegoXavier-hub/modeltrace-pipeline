# -*- coding: utf-8 -*-
"""Confere se as bibliotecas do pipeline estao instaladas e importam sem erro.

Chamado por instalar.bat ao final da instalacao. Nao acessa banco nenhum --
so verifica o ambiente Python.
"""
from __future__ import annotations

import importlib
import sys

# (modulo a importar, nome exibido, para que serve no projeto)
LIBS = [
    ("pymongo", "pymongo", "MongoDB"),
    ("redis", "redis", "Redis"),
    ("neo4j", "neo4j", "Neo4j"),
    ("streamlit", "streamlit", "interface web"),
    ("pandas", "pandas", "tabelas"),
    ("pyarrow", "pyarrow", "tabelas do Streamlit"),
    ("constelario", "constelario", "grafo de conhecimento"),
]


def main() -> int:
    falhou = False
    for modulo, nome, uso in LIBS:
        try:
            mod = importlib.import_module(modulo)
        except Exception as exc:  # noqa: BLE001 - qualquer falha de import interessa aqui
            falhou = True
            print(f"  [FALHA] {nome:<12} nao importou: {exc}")
            continue
        versao = getattr(mod, "__version__", "?")
        print(f"  [OK] {nome:<12} v{versao:<9} ({uso})")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
