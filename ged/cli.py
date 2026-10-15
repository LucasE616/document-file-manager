"""Linha de comando: busca e contagem sem abrir a janela.

    python main.py buscar "D:\\ACERVO\\2019" --filtro "Favorecido=CEMIG" --saida relatorio.txt
    python main.py contar "D:\\ACERVO\\2019" --tipos pdf,tif --aprofundada --saida contagem.xlsx

Útil para conferência rápida, para gerar relatório agendado e para testes.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import NOME, __version__, catalogo as cat, datas, leitores, perfil as perfis
from .texto import formatar_inteiro, normalizar

ALIASES_TIPOS = {
    "pdf": (".pdf",), "pdfa": (".pdfa",), "tif": (".tif", ".tiff"), "tiff": (".tif", ".tiff"),
    "png": (".png",), "jpg": (".jpg", ".jpeg"), "jpeg": (".jpg", ".jpeg"), "svg": (".svg",),
}


def _par_filtro(texto: str) -> tuple[str, str]:
    if "=" not in texto:
        raise argparse.ArgumentTypeError(f'use CAMPO=VALOR (recebido: "{texto}")')
    campo, valor = texto.split("=", 1)
    if not campo.strip():
        raise argparse.ArgumentTypeError(f'o nome do campo está vazio em "{texto}"')
    return campo.strip(), valor


def _data(texto: str) -> str:
    if not datas.periodo_valido(texto):
        raise argparse.ArgumentTypeError(f'data não reconhecida: "{texto}" (use 2019, 11/2019 ou 29/11/2019)')
    return texto


def _tipos(texto: str) -> set[str]:
    if normalizar(texto) == "todos":
        return set(leitores.EXTENSOES_SUPORTADAS)
    extensoes: set[str] = set()
    for item in texto.split(","):
        chave = item.strip().lower().lstrip(".")
        if not chave:
            continue
        if chave not in ALIASES_TIPOS:
            raise argparse.ArgumentTypeError(f'tipo desconhecido: "{item}" (use {", ".join(ALIASES_TIPOS)} ou todos)')
        extensoes.update(ALIASES_TIPOS[chave])
    if not extensoes:
        raise argparse.ArgumentTypeError("informe ao menos um tipo")
    return extensoes


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description=f"{NOME} {__version__}")
    parser.add_argument("--versao", action="version", version=f"{NOME} {__version__}")
    sub = parser.add_subparsers(dest="comando")

    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("diretorio", help="Pasta do acervo.")
    comum.add_argument("--sem-subpastas", action="store_true", help="Não descer nas subpastas.")
    comum.add_argument("--perfil", metavar="JSON", help="Perfil de tipos documentais (ver exemplos/ged_perfil.json).")
    comum.add_argument("--saida", action="append", metavar="ARQUIVO", default=[],
                       help="Relatório a gravar: .txt, .csv ou .xlsx (repetível).")
    comum.add_argument("--base-data", choices=list(cat.BASES_DATA), default=cat.BASE_CRIACAO,
                       help="Qual data do arquivo usar nos períodos (padrão: criacao).")

    b = sub.add_parser("buscar", parents=[comum], help="Busca no acervo e lista o resultado.")
    b.add_argument("--termo", default="", help="Texto livre a procurar.")
    b.add_argument("--filtro", action="append", type=_par_filtro, default=[], metavar="CAMPO=VALOR",
                   help="Filtro por campo de índice (repetível).")
    b.add_argument("--conteudo", action="store_true", help="Procurar também dentro do texto dos PDFs.")
    b.add_argument("--tipo", help="Tipo do perfil (despesa, licitacao, legislacao...) ou outro.")
    b.add_argument("--indices", help='Com --tipo outro: índices a buscar, separados por vírgula.')
    b.add_argument("--indice-de", type=_data, default="", help="Início do período sobre a data do índice.")
    b.add_argument("--indice-ate", type=_data, default="", help="Fim do período sobre a data do índice.")
    b.add_argument("--arquivo-de", "--criacao-de", type=_data, default="", help="Início do período sobre a data do arquivo.")
    b.add_argument("--arquivo-ate", "--criacao-ate", type=_data, default="", help="Fim do período sobre a data do arquivo.")
    b.add_argument("--csv", metavar="ARQUIVO", help=argparse.SUPPRESS)
    b.add_argument("--txt", metavar="ARQUIVO", help=argparse.SUPPRESS)
    b.add_argument("--limite", type=int, default=10, help="Quantos resultados listar no terminal.")

    c = sub.add_parser("contar", parents=[comum], help="Conta páginas e audita o acervo.")
    c.add_argument("--tipos", type=_tipos, default=set(leitores.EXTENSOES_PADRAO),
                   help="pdf,pdfa,tif,png,jpg,svg ou todos (padrão: pdf,pdfa).")
    c.add_argument("--de", type=_data, default="", help="Início do período (2019, 11/2019, 29/11/2019).")
    c.add_argument("--ate", type=_data, default="", help="Fim do período.")
    c.add_argument("--aprofundada", action="store_true", help="SHA-256, PDF/A declarado e integridade das imagens.")
    c.add_argument("--problemas", type=int, default=15, help="Quantos problemas listar no terminal.")

    sub.add_parser("testes", help="Roda os testes automáticos.")
    return parser


def _carregar(args) -> cat.Catalogo:
    if args.perfil:
        perfis.definir(perfis.carregar_arquivo(args.perfil))
    print(f"Lendo {args.diretorio} ...")
    catalogo = cat.varrer(args.diretorio, incluir_subpastas=not args.sem_subpastas)
    print(
        f"  {formatar_inteiro(catalogo.total_documentos)} documento(s), "
        f"{formatar_inteiro(catalogo.arquivos_encontrados)} arquivo(s), {catalogo.xmls_lidos} índice(s)"
        + (f", {len(catalogo.xmls_tolerantes)} em modo tolerante" if catalogo.xmls_tolerantes else "")
        + (f", {len(catalogo.registros_duplicados)} registro(s) duplicado(s)" if catalogo.registros_duplicados else "")
    )
    return catalogo


def _buscar(args) -> int:
    from .busca import Criterios, buscar
    from .conteudo import CacheConteudo
    from .contagem import ler_paginas_faltantes
    from .exportar import busca as exportar_busca

    catalogo = _carregar(args)
    print(f"  Campos de índice: {', '.join(catalogo.vocabulario) or '(nenhum)'}")
    if catalogo.campos_data:
        print(f"  Campos de data: {', '.join(catalogo.campos_data)}")
    grupos, sem_tipo = cat.agrupar_por_tipo(catalogo)
    print("  Tipos: " + ", ".join(f"{g.rotulo} ({g.total_documentos})" for g in grupos)
          + (f", outros ({sem_tipo})" if sem_tipo else ""))
    ler_paginas_faltantes(catalogo)

    if args.tipo:
        pedido = normalizar(args.tipo)
        if pedido.startswith("outro"):
            indices = [i.strip() for i in (args.indices or "").split(",") if i.strip()]
            desconhecidos = [i for i in indices if i not in catalogo.vocabulario]
            if desconhecidos:
                print(f"\nÍndice(s) não encontrado(s): {', '.join(desconhecidos)}", file=sys.stderr)
                return 2
            catalogo = cat.subcatalogo_por_indices(catalogo, indices)
        else:
            escolhido = next((g for g in grupos if pedido in (normalizar(g.chave), normalizar(g.rotulo))
                              or normalizar(g.rotulo).startswith(pedido)), None)
            if escolhido is None:
                opcoes = ", ".join(g.chave for g in grupos)
                print(f"\nTipo '{args.tipo}' não reconhecido. Use {opcoes} ou outro (com --indices).", file=sys.stderr)
                return 2
            catalogo = cat.subcatalogo(catalogo, escolhido)
        print(f"  Tipo selecionado: {catalogo.tipo_ativo}")

    criterios = Criterios(
        termo=args.termo, escopo_conteudo=args.conteudo, filtros=dict(args.filtro),
        indice_de=args.indice_de, indice_ate=args.indice_ate,
        arquivo_de=args.arquivo_de, arquivo_ate=args.arquivo_ate, base_data_arquivo=args.base_data,
    )
    resultado = buscar(catalogo, criterios, cache=CacheConteudo() if args.conteudo else None)

    print(f"\nResultado: {formatar_inteiro(resultado.total_documentos)} documento(s), "
          f"{formatar_inteiro(resultado.total_paginas)} página(s)")
    for documento in resultado.documentos[: args.limite]:
        print(f"  - {documento.nome_arquivo}  ({documento.paginas if documento.paginas is not None else '?'} pág.)")
    if resultado.total_documentos > args.limite:
        print(f"  ... e mais {formatar_inteiro(resultado.total_documentos - args.limite)}")
    for observacao in exportar_busca.observacoes(catalogo, resultado):
        print(f"  ! {observacao}")

    for destino in args.saida + [x for x in (args.csv, args.txt) if x]:
        exportar_busca.exportar(destino, catalogo, resultado, criterios)
        print(f"Relatório salvo em {destino}")
    return 0


def _contar(args) -> int:
    from .contagem import OpcoesContagem, contar
    from .exportar import contagem as exportar_contagem

    catalogo = _carregar(args)
    opcoes = OpcoesContagem(
        extensoes=args.tipos,
        data_de=datas.limite_periodo(args.de, inicio=True),
        data_ate=datas.limite_periodo(args.ate, inicio=False),
        base_data=args.base_data,
        aprofundada=args.aprofundada,
    )
    if opcoes.data_de and opcoes.data_ate and opcoes.data_de > opcoes.data_ate:
        print("A data inicial não pode ser depois da data final.", file=sys.stderr)
        return 2
    print(f"  Contando {opcoes.descrever_tipos()} — {opcoes.descrever_periodo()} ...")
    resultado = contar(catalogo, opcoes)

    print(f"\nArquivos: {formatar_inteiro(resultado.total_arquivos)}   "
          f"Páginas: {formatar_inteiro(resultado.total_paginas)}   "
          f"Com erro: {formatar_inteiro(resultado.total_erros)}   "
          f"Problemas: {formatar_inteiro(resultado.total_problemas)}")
    if resultado.fora_do_periodo:
        print(f"  {formatar_inteiro(resultado.fora_do_periodo)} arquivo(s) fora do período")
    for categoria, quantidade in resultado.problemas_por_categoria():
        print(f"  {categoria}: {formatar_inteiro(quantidade)}")
    if args.problemas:
        listados = [p for p in resultado.problemas if p.categoria != "Arquivo sem registro de índice"][: args.problemas]
        for p in listados:
            print(f"    - [{p.categoria}] {p.arquivo}" + (f" — {p.detalhe}" if p.detalhe else ""))
    if resultado.hash_conjunto:
        print(f"  Hash do conjunto: {resultado.hash_conjunto}")

    for destino in args.saida:
        exportar_contagem.exportar(destino, resultado, catalogo.incluir_subpastas)
        print(f"Relatório salvo em {destino}")
    return 0


def _testes() -> int:
    import unittest

    raiz = Path(__file__).resolve().parent.parent
    suite = unittest.defaultTestLoader.discover(str(raiz / "tests"), top_level_dir=str(raiz))
    resultado = unittest.TextTestRunner(verbosity=1).run(suite)
    if os.environ.get("GITHUB_ACTIONS"):
        # Vira anotação no resumo da execução, legível sem abrir o log
        for teste, rastro in (resultado.failures + resultado.errors)[:10]:
            texto = rastro[-3000:].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title={teste.id()}::{texto}")
    return 0 if resultado.wasSuccessful() else 1


def _compatibilizar(argv: list[str]) -> list[str]:
    """Aceita a forma antiga `--buscar DIR` do GED Offline 0.1."""
    if "--buscar" in argv:
        i = argv.index("--buscar")
        if i + 1 < len(argv):
            return ["buscar", argv[i + 1]] + argv[:i] + argv[i + 2:]
    if "--selftest" in argv:
        return ["testes"]
    return argv


def principal(argv: list[str]) -> int:
    parser = montar_parser()
    args = parser.parse_args(_compatibilizar(argv))
    if args.comando is None:
        parser.print_help()
        return 2
    if args.comando == "testes":
        return _testes()
    from . import dependencias

    dependencias.garantir_no_terminal()
    try:
        if args.comando == "buscar":
            return _buscar(args)
        if args.comando == "contar":
            return _contar(args)
    except (FileNotFoundError, perfis.ErroPerfil, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    return 0
