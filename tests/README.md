# Testes do GED Offline

Toda alteração no programa vem acompanhada de teste. Este guia diz como
rodar, onde colocar e como escrever cada tipo.

## Rodar

```bash
python main.py testes                       # tudo (sem tela, os de interface são pulados)
xvfb-run -a python main.py testes           # Linux sem tela: inclui os de interface
python -m unittest tests.test_tipos         # um arquivo
python -m unittest tests.test_tipos.TestCriarTipo.test_validacoes   # um teste
```

Cobertura (a mesma conta que o CI faz):

```bash
python -m pip install coverage
python -m coverage run main.py testes
python -m coverage report                   # falha abaixo do piso de .coveragerc
python -m coverage html                     # relatório navegável em htmlcov/
```

Não há dependência para testar: `unittest` é da biblioteca padrão. Sem o
pypdfium2 ou o Pillow, os testes que precisam deles são pulados, e o resto
roda. O CI roda tudo duas vezes, sem e com esses componentes, no Windows e
no Linux, em Python 3.10 e 3.13.

## As três camadas

| Camada | Onde | Para quê |
|---|---|---|
| **Unitários** | `test_<módulo>.py` | uma função ou classe do núcleo (`ged/`), sem interface |
| **Regressão** | `test_regressao.py`, e testes marcados com `Correção:` nos demais | prender um defeito que já existiu, para ele não voltar |
| **Interface** | `test_gui.py` | a janela de verdade: leitura do diretório, diálogos, tarefas em segundo plano |

### Unitários

Um arquivo por módulo de `ged/` (`busca.py` → `test_busca.py`). Herde de
`TesteComPasta` sempre que o teste tocar em arquivo ou no perfil:

```python
from tests.base import TesteComPasta, sem_pdf
from tests.gerador import gerar_pdf, indice_xml

class TestAlgo(TesteComPasta):
    @sem_pdf                                   # pula sem o pypdfium2
    def test_conta_paginas(self):
        gerar_pdf(self.pasta / "a.pdf", 3)     # PDF real, gerado na hora
        (self.pasta / "i.xml").write_bytes(indice_xml([{"Favorecido": "X", "_arquivo": "a.pdf"}]))
        ...
```

O que `TesteComPasta` garante:

- `self.pasta`: pasta temporária nova, apagada no fim;
- perfil padrão em uso, mesmo que exista um `ged_perfil.json` na máquina;
- `pasta_do_programa()` aponta para `self.pasta_programa`: **nenhum teste
  grava no repositório**;
- `self.perfil_com_tipo("Contratos", ["Contratado", "Objeto"])` cria um tipo
  documental e devolve a chave.

Para a linha de comando, use `rodar_cli("buscar", str(self.pasta), ...)`,
que devolve `(código, saída, erros)`.

**Nada de dado real** nos testes: nem arquivo do acervo, nem caminho fixo
como `C:\Users\...`. Gere o que precisar com `tests/gerador.py`.

### Regressão

Quando corrigir um defeito, **escreva primeiro o teste que falha** e só
depois corrija. Convenção:

```python
def test_reexportacao_nao_conta_em_dobro(self):
    """Correção: um PDF citado em dois XML entrava duas vezes, com as páginas somadas em dobro."""
```

- o nome diz o comportamento **certo**;
- a docstring começa com `Correção:` e descreve o defeito como o usuário o via;
- confira que o teste **falha no código antigo** (`git stash` da correção,
  rodar, `git stash pop`). Teste de regressão que passa com o defeito não
  protege nada.

Defeitos de um módulo ficam no `test_<módulo>.py` dele; os que atravessam
módulos, ou os de desempenho e memória, vão para `test_regressao.py`. Os da
interface ficam em `test_gui.py`, na classe `TestRegressaoInterface`.

### Interface

`test_gui.py` abre a janela (`App`), lê um acervo gerado e aciona os
métodos dos botões. Regras:

- herde de `TesteJanela`: ela cria e fecha a janela, desliga a instalação
  automática de componentes e **reprova o teste se houver exceção dentro de
  um callback do Tk** (que, no programa, só abriria uma janela de erro);
- diálogos modais travariam o teste: abra o diálogo diretamente e chame os
  métodos (`dialogo.criar()`), ou troque-o por um dublê com `mock.patch`;
- caixas de mensagem (`messagebox`) e de arquivo (`filedialog`) sempre com
  `mock.patch`;
- espere por uma condição com `self.esperar(lambda: ...)` e deixe o tempo
  correr com `self.bombear(segundos)`. Nunca use `time.sleep` puro: a
  interface só anda com `update()`;
- teste de corrida entre threads precisa ser determinístico: controle o
  tempo com `threading.Event` e, se preciso, mude o intervalo da fila
  (veja `test_tarefa_interrompida_nao_libera_a_interface_da_seguinte`).

No CI do Windows, `GED_EXIGIR_INTERFACE=1` faz os testes de interface
falharem em vez de serem pulados — assim não se perde a camada sem perceber.

## Checklist de uma alteração

- [ ] teste novo para o comportamento novo (unitário e, se houver tela, de interface);
- [ ] defeito corrigido → teste de regressão que falha sem a correção;
- [ ] `python main.py testes` passa, com e sem os componentes;
- [ ] a cobertura não caiu abaixo do piso (`python -m coverage report`);
- [ ] subiu a cobertura? suba também o `fail_under` do `.coveragerc`.
