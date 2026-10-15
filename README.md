# GED Offline

Consulta, contagem de páginas e auditoria do acervo digitalizado — Despesas, Licitações, Legislações ou qualquer outro tipo — direto no diretório onde os documentos estão, **sem internet, sem banco de dados e sem custo**.

Junta num único programa dois projetos anteriores:

- **[GED Offline](https://github.com/LucasE616/ged-offline)** — busca no acervo pelos índices XML do Kodak Capture / PaperCapture, pelo nome do arquivo e pelo conteúdo dos PDFs;
- **[Contador de Páginas](https://github.com/LucasE616/PDF_page_counter)** — contagem de páginas de PDF, TIFF, PNG, JPG e SVG, com filtro por período e relatório.

Os dois trabalham sobre a mesma leitura do diretório, e juntos fazem algo que nenhum fazia sozinho: **conferir o que os índices dizem contra o que os arquivos realmente têm**.

Nada é gravado no acervo nem fora dele: os únicos arquivos que saem do programa são os relatórios que você mandar exportar.

## Como usar

### Executável (recomendado)

Baixe `GED-Offline-<versão>-windows.zip` na página de [Releases](../../releases), descompacte e abra **GED Offline.exe**. Não há nada para instalar — o Python e todos os componentes já vêm dentro da pasta. Funciona sem internet.

### Como script

Precisa do Python 3.10 ou mais novo (o instalador do python.org já traz o Tkinter).

```bash
python main.py
```

No Windows, um duplo clique em **GED Offline.pyw** abre o programa sem a janela de console.

Na primeira execução o programa instala sozinho os dois componentes de leitura (veja [Componentes](#componentes)). Sem internet nesse momento, ele continua funcionando — a busca por nome e pelos índices XML não depende deles — e tenta de novo na próxima abertura.

## A janela

1. **Escolher...** e selecione a pasta do acervo. Deixe *Subpastas* marcado para varrer a árvore inteira.
2. O programa lê o diretório uma vez e monta as duas abas a partir do que encontrou.

### Aba Consulta

- Se a pasta tiver mais de um tipo de documento, o programa pergunta qual você quer consultar (veja [Tipo de documento](#tipo-de-documento)).
- Busque por texto livre, pelos campos de índice, por período, ou por tudo junto.
- Clique no cabeçalho de uma coluna para ordenar; clique de novo para inverter.
- Selecionar uma linha mostra a miniatura da primeira página e uma ficha do arquivo (páginas, tamanho, datas).
- Duplo clique abre o arquivo. O botão direito, ou os botões ao lado da miniatura, oferecem **Abrir pasta do arquivo**, que abre o Explorer já com o documento selecionado.
- **Exportar TXT**, **CSV** ou **XLSX** leva o resultado embora.

### Aba Contagem e auditoria

- Marque os tipos de arquivo (PDF, PDF/A, TIFF, PNG, JPG, SVG) e, se quiser, um período.
- **Contar páginas** abre cada arquivo e conta as páginas de verdade — TIFF multipágina conta cada quadro.
- O resultado aparece em cartões (arquivos, páginas, com erro, problemas, tamanho) e em três listas:
  - **Totais** agrupados por extensão, tipo documental, pasta, ano, mês, situação ou PDF/A;
  - **Problemas** encontrados na auditoria (duplo clique abre a pasta do arquivo);
  - **Arquivos**, um por linha, com páginas, páginas segundo o índice, situação e datas.
- **Conferência aprofundada** lê cada arquivo por inteiro para calcular o SHA-256, identificar a conformidade PDF/A declarada e verificar a integridade das imagens. É mais lenta, por isso é opcional.

#### O que a auditoria aponta

| Problema | O que significa |
|---|---|
| Páginas do índice diferentes do arquivo | o XML diz um número de páginas e o arquivo tem outro |
| Registro de índice sem arquivo | o XML cita um arquivo que não está no diretório |
| Registro duplicado no índice | o mesmo arquivo citado em mais de um XML (reexportação de lote) — contado uma vez só |
| Arquivo homônimo vinculado por aproximação | há arquivos com o mesmo nome em pastas diferentes e o vínculo com o índice foi deduzido |
| Arquivo corrompido, protegido por senha, sem páginas, inacessível | o arquivo não pôde ser lido, e o motivo |
| Conteúdo idêntico a outro arquivo | dois arquivos com o mesmo SHA-256 (conferência aprofundada) |
| Data do arquivo desconhecida | com filtro de período, o arquivo sem a data escolhida — listado, não descartado em silêncio |
| Índice XML malformado / ilegível | o XML foi lido em modo tolerante, ou não pôde ser lido |
| Arquivo sem registro de índice | informativo: nenhum XML cita o arquivo |

O relatório da conferência aprofundada traz também o **hash do conjunto**: o SHA-256 da lista de todos os arquivos com seus hashes. Meses depois, recalcular e obter o mesmo valor prova que o conjunto contado é exatamente aquele.

## Tipo de documento

Toda vez que um diretório é lido, a aba Consulta pergunta qual tipo documental você vai consultar:

- **Despesas**, **Licitações** ou **Legislações** — cada um mostra quantos documentos e páginas dele existem na pasta. Um tipo sem nenhum documento aparece apagado. O tipo com mais documentos já vem marcado: confirmar é só apertar Enter.
- **Outro tipo de documento** — você marca quais índices quer buscar; entre parênteses aparece em quantos documentos cada índice está preenchido. Os índices marcados viram os campos de busca e as colunas, e definem quais documentos aparecem: os que têm ao menos um deles preenchido.

O botão **Tipo:** reabre a pergunta a qualquer momento. Quem está só na aba de contagem não é interrompido: a pergunta espera até a aba Consulta ser aberta.

Para enquadrar cada documento, as pistas são tentadas da mais específica para a mais genérica: o padrão do nome do arquivo (`despesa_…`, `licitacao_…`), depois o campo *Título* do índice, depois o nome das pastas entre o documento e o diretório escolhido. Pastas acima do diretório escolhido não contam, e palavras curtas precisam aparecer inteiras — "Leilão", que é modalidade de licitação, não é confundido com lei.

### Perfil do acervo

Os tipos documentais e os padrões de nome não estão escritos no código: estão num perfil. O perfil padrão atende Despesas, Licitações e Legislações. Para outro acervo, copie [`exemplos/ged_perfil.json`](exemplos/ged_perfil.json) para a pasta do programa com o nome `ged_perfil.json` e edite — o programa passa a usá-lo, sem alterar nada no código.

## Datas e períodos

Os campos de data são reconhecidos pelo **conteúdo**, não pelo nome: o programa olha os valores e marca como data o campo que contém datas, seja ele `Data de Pagto`, `Data Ass` ou `Data`.

O mesmo arquivo de índice grava `2019-11-29` na maioria dos registros e `01-11-2019` em outros, e o usuário digita `29/11/2019`, que não é nenhum dos dois. Buscar por qualquer um desses formatos encontra os outros. A busca também aceita datas incompletas:

| Você digita | Encontra |
|---|---|
| `2019` | o ano inteiro |
| `11/2019` | o mês inteiro |
| `29/11/2019` ou `29/11/19` | o dia exato |

Os mesmos formatos valem nos períodos. `de 2019 até 2019` pega o ano inteiro, não um dia só. Campos que não são datas continuam funcionando como texto comum: digitar `05/2019` no campo Número procura esse trecho, e não maio de 2019.

O período da **data do arquivo** pode usar três bases:

- **criação do arquivo** — a data em que o arquivo foi criado no disco;
- **modificação do arquivo**;
- **data interna do PDF** — gravada dentro do PDF pelo software que o gerou.

> Copiar o acervo para outro disco muda a data de criação para o dia da cópia. A data interna do PDF não muda — use-a quando o acervo tiver sido copiado.

## Os três escopos de busca

O texto livre é procurado nos escopos marcados, em **OU** — um documento entra no resultado se o termo aparecer em qualquer um deles:

| Escopo | Custo | O que encontra |
|---|---|---|
| **nome** | instantâneo | o termo no nome do arquivo |
| **índice** | instantâneo | o termo em qualquer campo de índice |
| **conteúdo do PDF** | abre arquivos | o termo em qualquer página do documento |

Os **campos de índice** funcionam ao contrário: restringem, e valem todos ao mesmo tempo.

A busca por conteúdo vem desligada por padrão porque alarga bastante o resultado. Quando ligada, ela abre apenas os PDFs que ainda não casaram pelo nome ou pelo índice, e guarda o texto lido na memória — a segunda busca responde na hora. O botão **Ler conteúdo de todos** antecipa essa leitura.

A busca ignora acentuação e caixa nos dois lados: `municipio` encontra `MUNICÍPIO`.

## Contagem de páginas na consulta

O rodapé da consulta mostra o total do diretório e o total do resultado. As páginas vêm do campo `Page count in document` do XML; para arquivos sem índice, são contadas em segundo plano logo depois da leitura do diretório. Depois de uma contagem na outra aba, a contagem real do arquivo passa a valer no lugar da do índice. Se algum documento ficar sem contagem, o rodapé avisa em vez de somar um total incompleto sem dizer nada.

## Índices dinâmicos

O vocabulário de busca vem dos próprios XML: uma pasta de despesas dá Favorecido, Data de Pagto, Valor e Histórico; uma de licitações dá Modalidade, Objeto e Fornecedor; uma de legislações dá Tipo, Número, Ementa e Data.

Para documentos cujo índice veio incompleto, os metadados são buscados em três fontes, nesta ordem:

1. **Campos do XML** — `name="Numero" value="12030"`
2. **Nome do arquivo** — `Despesa_2019_06953-…pdf` → ano 2019, nº 06953
3. **Caminho da pasta** — `…\licitacao\2017\licitacao_098_76` → nº 098, 2017

Arquivos com o mesmo nome em pastas diferentes são todos catalogados. O registro do índice é ligado ao arquivo da mesma pasta do XML, ou ao que mais combina com o *Batch Location*; quando a escolha é incerta, a auditoria avisa.

## Acervos com defeito

Os exports antigos têm problemas que são rotina, não exceção, e o programa atravessa todos sem descartar documento:

- XML que declara UTF-8 mas está gravado em Windows-1252
- XML malformado, com valores longos truncados sem fechar as aspas
- Campos vazios e datas em formatos diferentes no mesmo arquivo
- O mesmo lote exportado duas vezes
- PDF sem camada de texto, corrompido, protegido por senha ou sem páginas
- Pastas sem permissão de leitura ou disco de rede desconectado no meio da leitura

## Exportação

| Formato | Consulta | Contagem e auditoria |
|---|---|---|
| **TXT** | relatório legível com cabeçalho (diretório, data, escopo, critérios) e totais | resumo, totais por extensão, tipo e ano, problemas por categoria e lista de arquivos |
| **CSV** | uma coluna por índice, mais arquivo, páginas, origem e caminho | uma linha por arquivo, com páginas, situação, datas e (na aprofundada) PDF/A e SHA-256 |
| **XLSX** | abas Resumo e Resultado | abas Resumo, Arquivos, Problemas e uma por agrupamento |

CSV com separador `;` e UTF-8 com BOM — é o que faz o Excel em português abrir com acentos e colunas corretos sem assistente. Todos os relatórios trazem as ressalvas junto do total.

## Linha de comando

Útil para conferência rápida, para relatórios agendados e para automação:

```bash
python main.py buscar "D:\ACERVO\2019" --filtro "Favorecido=CEMIG" --saida relatorio.txt
python main.py contar "D:\ACERVO\2019" --tipos pdf,tif --de 2019 --ate 2019 --aprofundada --saida contagem.xlsx
```

- `buscar`: `--termo`, `--filtro CAMPO=VALOR` (repetível), `--conteudo`, `--tipo despesa|licitacao|legislacao|outro`, `--indices "A,B"` (com `--tipo outro`), `--indice-de`, `--indice-ate`, `--arquivo-de`, `--arquivo-ate`, `--limite`
- `contar`: `--tipos pdf,pdfa,tif,png,jpg,svg|todos`, `--de`, `--ate`, `--aprofundada`, `--problemas N`
- comuns: `--saida ARQUIVO` (.txt, .csv ou .xlsx, repetível), `--base-data criacao|modificacao|interna`, `--sem-subpastas`, `--perfil ARQUIVO.json`

`python main.py --help` e `python main.py buscar --help` listam tudo. A forma antiga `python main.py --buscar DIR` continua aceita.

## Componentes

Tudo o que é essencial usa só a biblioteca padrão do Python: interface (Tkinter), XML, CSV, XLSX e testes. Para ler os arquivos, dois componentes gratuitos e de licença permissiva:

| Componente | Uso | Licença |
|---|---|---|
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | PDFs: páginas, texto, miniatura e data interna — usa o PDFium, o motor de PDF do Chrome | BSD-3 / Apache-2.0 |
| [Pillow](https://python-pillow.org) | TIFF, PNG e JPG; miniaturas | HPND |

O executável já os traz embutidos. Rodando como script, o programa os instala sozinho na primeira execução: primeiro a partir da pasta `pacotes/` ao lado do programa, se existir; senão pela internet, testando antes a conexão por poucos segundos.

Para instalar o script em máquinas **sem internet**, rode `python ferramentas/baixar_pacotes.py` numa máquina com internet e copie a pasta do programa, já com `pacotes/`, para as máquinas de destino.

## Desenvolvimento

```bash
python main.py testes                  # testes automáticos (unittest, sem dependências)
python ferramentas/gerar_exe.py        # gera dist/GED Offline/ e o .zip para distribuir
```

O `gerar_exe.py` cria um ambiente isolado em `.build/`, instala ali o PyInstaller e os componentes, e empacota tudo — nada é instalado no seu Python.

No GitHub, dois workflows gratuitos para repositório público:

- **Testes** — a cada push, em Windows e Linux, Python 3.10 e 3.13, com e sem os componentes;
- **Executável Windows** — ao criar uma tag `v*` (`git tag v1.0.0 && git push origin v1.0.0`), gera o `.zip` e o publica na página de Releases.

### Estrutura

```
main.py                 ponto de entrada: interface ou linha de comando
GED Offline.pyw         abre a interface sem console (duplo clique no Windows)
ged/
  catalogo.py           varredura, catálogo em memória, vínculo índice ↔ arquivo
  xml_parser.py         leitura tolerante dos índices XML
  nomes.py              metadados do nome do arquivo e do caminho
  perfil.py             tipos documentais e padrões de nome (perfil JSON)
  datas.py              datas em qualquer formato e períodos
  busca.py              filtros por campo, período e texto livre nos três escopos
  conteudo.py           texto dos PDFs, com cache de sessão
  leitores.py           leitura de cada formato: páginas, texto, miniatura, SHA-256, PDF/A
  contagem.py           contagem de páginas, auditoria e agrupamentos
  dependencias.py       instalação automática dos componentes
  cli.py                linha de comando
  exportar/             relatórios TXT, CSV e XLSX (o XLSX sem dependência)
  gui/                  interface Tkinter: janela, aba Consulta, aba Contagem
tests/                  testes automáticos, com arquivos de exemplo gerados na hora
ferramentas/            gerar o executável; baixar pacotes para instalação sem internet
exemplos/               perfil do acervo para editar
```

## Limitações

- Sem OCR — PDFs que são só imagem não têm o que ser procurado por conteúdo. Um OCR gratuito exigiria instalar o Tesseract à parte, o que o programa evita.
- A leitura do diretório é refeita a cada abertura, já que nada é guardado. Numa pasta de 2.500 documentos isso leva poucos segundos.
- A conformidade PDF/A é a **declarada** no arquivo; o programa não valida o PDF contra a norma.
- A data interna do PDF só é conhecida dos arquivos já abertos pela contagem de páginas (os sem índice são abertos logo após a leitura do diretório; os demais, ao usar a aba Contagem).

## Licença

[Mozilla Public License 2.0](LICENSE).
