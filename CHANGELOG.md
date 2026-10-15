# Histórico de versões

## 1.0.0 — 15/10/2026

Primeira versão unificada: o **GED Offline 0.1** e o **Contador de Páginas** num programa só, sobre a mesma leitura do diretório.

### Novo

- Aba **Contagem e auditoria**: contagem real de páginas de PDF, PDF/A, TIFF, PNG, JPG e SVG, cruzada com os índices XML.
- Auditoria: páginas do índice × páginas do arquivo, registro sem arquivo, registro duplicado, homônimo vinculado por aproximação, arquivo corrompido / protegido por senha / sem páginas / inacessível, conteúdo idêntico, XML malformado.
- Conferência aprofundada opcional: SHA-256 de cada arquivo, **hash do conjunto**, conformidade PDF/A declarada (XMP) e integridade das imagens.
- Totais agrupados por extensão, tipo documental, pasta, ano, mês, situação e PDF/A.
- Exportação **XLSX** nas duas abas, sem dependência extra.
- Período pela **data interna do PDF** ou pela modificação, além da criação — a criação muda quando o acervo é copiado.
- Arquivos TIFF, PNG e JPG também entram na consulta, com miniatura.
- Ordenação da tabela por coluna (números e datas ordenam como números e datas).
- Ficha do documento ao lado da miniatura: páginas, tamanho, datas, situação.
- **Perfil do acervo** em JSON (`ged_perfil.json`): tipos documentais e padrões de nome fora do código.
- **Executável Windows** (`ferramentas/gerar_exe.py`), com tudo embutido: o usuário não instala nada.
- Instalação sem internet a partir da pasta `pacotes/` (`ferramentas/baixar_pacotes.py`).
- Linha de comando com subcomandos `buscar` e `contar`, saída em TXT/CSV/XLSX.
- Testes automáticos com `unittest` (80 testes), arquivos de exemplo gerados na hora — sem dados reais nem caminhos fixos.
- GitHub Actions: testes em Windows e Linux; geração do executável a cada tag de versão.

### Trocado

- **PyMuPDF → pypdfium2** para ler PDFs. O PyMuPDF é AGPL; o pypdfium2 é BSD/Apache e usa o motor de PDF do Chrome. O programa continua gratuito para desenvolver, usar e distribuir, sem obrigações de licença.

### Corrigido — vindo do GED Offline 0.1

- PDFs com o **mesmo nome em pastas diferentes** viravam um documento só; os outros sumiam do catálogo e do total de páginas.
- Um arquivo citado em **dois XML** (reexportação de lote) entrava duas vezes, com as **páginas somadas em dobro**.
- Datas interpretadas de forma permissiva: `1012019` virava 09/01/1012 e `3112020` virava 31/01/2020; números de empenho de 8 dígitos transformavam o campo em "campo de data".
- `parece_campo_de_data`: `min(minimo, 1)` anulava o parâmetro `minimo`, e um único valor decidia o tipo do campo.
- Busca por data aplicada a qualquer campo: `05/2019` digitado no campo Número casava com o empenho `12052019`.
- Um arquivo inacessível durante a leitura (`stat()` falhando) **derrubava a varredura inteira**; pastas sem permissão eram ignoradas sem aviso.
- O texto dos PDFs era normalizado de novo **a cada busca** por conteúdo; agora fica em memória já normalizado.
- Os períodos eram interpretados de novo para cada documento.
- A miniatura era gerada na thread da interface, congelando a janela em PDF grande ou em rede.
- `--filtro CAMPO` sem `=` quebrava com `ValueError`.
- Período digitado errado era ignorado em silêncio; agora o programa avisa.
- Documentos aninhados em elemento de lote no XML não eram lidos (`findall` só olhava filhos diretos).
- Nome do arquivo gravado com o caminho da estação de digitalização não era vinculado.
- O autoteste dependia de arquivos em `C:\Users\...\Downloads`.

### Corrigido — vindo do Contador de Páginas

- A thread de trabalho chamava o Tkinter (`root.after`) a cada arquivo — não é seguro e, em pastas grandes, inundava a fila de eventos até a janela travar. Agora a comunicação é por fila, com no máximo 10 atualizações por segundo.
- O log de detalhes crescia sem limite; foi substituído por tabelas.
- CSV separado por **vírgula**, que no Excel em português não separa as colunas; e o resumo no topo quebrava a tabela.
- Sem internet, a tela ficava **até 10 minutos** em "Verificando..." (duas tentativas de 300 s) antes do erro.
- Logo após o `pip install`, o pacote podia continuar "não encontrado" (caches de importação e pasta do usuário fora do caminho).
- `pip install --user` era tentado mesmo dentro de ambiente virtual, onde é inválido.
- Contar quadros de imagem decodificava a imagem inteira (`img.load()`), lento em TIFFs grandes; imagens acima de ~179 megapixels eram recusadas como "bomba de descompressão".
- PDF protegido por senha, PDF sem páginas e PDF corrompido viravam o mesmo "erro" genérico.
- Arquivos com data ilegível eram **descartados em silêncio** quando havia filtro de período.
- Sem botão de cancelar.
- Números no formato americano (`1,234`).
- O checkbox "PDF/A" filtrava apenas a extensão `.pdfa`; o rótulo agora diz isso, e a conformidade PDF/A real é verificada pelo XMP.
- Dois scripts quase iguais (`contador_paginas_pdfa.pyw` e `File_Counter.pyw`).
- README exigia Python 3.14; o programa roda em 3.10 ou mais novo.

### Corrigido — encontrado durante a fusão

- O PDFium deixava **aberto** o arquivo que recusava (corrompido ou sem páginas): no Windows ele não podia ser movido nem apagado enquanto o programa estivesse aberto.
- Erros inesperados pelo `.pyw` (sem console) desapareciam; agora aparecem numa janela com o detalhe copiável.
