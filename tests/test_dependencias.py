"""Instalação automática — sem rede e sem pip de verdade."""
import sys
import unittest
from pathlib import Path
from unittest import mock

from ged import dependencias as dep

PACOTE = dep.Pacote("modulo_que_nao_existe_xyz", "pacote-xyz", "teste")


class TestDependencias(unittest.TestCase):
    def test_executavel_nao_instala_nada(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(dep.faltando(), [])

    def test_sem_internet_desiste_rapido_e_explica(self):
        with mock.patch.object(dep, "_garantir_pip", return_value=True), \
             mock.patch.object(dep, "pasta_pacotes", return_value=Path("/nao/existe")), \
             mock.patch.object(dep, "_tem_internet", return_value=False) as internet, \
             mock.patch.object(dep, "_pip") as pip:
            falhas = dep.instalar([PACOTE, PACOTE])
        self.assertEqual(internet.call_count, 1)  # testa a conexão uma vez só
        pip.assert_not_called()
        self.assertEqual(falhas[0][1], "sem conexão com a internet")
        self.assertIn("continua funcionando", dep.mensagem_de_falha(falhas))

    def test_pasta_local_tem_prioridade(self):
        with mock.patch.object(dep, "_garantir_pip", return_value=True), \
             mock.patch.object(dep, "pasta_pacotes", return_value=Path(__file__).parent), \
             mock.patch.object(dep, "_tem_internet") as internet, \
             mock.patch.object(dep, "_pip", return_value=(True, "")) as pip:
            dep.instalar([PACOTE])
        self.assertIn("--no-index", pip.call_args_list[0].args[0])
        internet.assert_not_called()

    def test_tenta_user_quando_falta_permissao(self):
        respostas = iter([(False, "Permission denied"), (True, "")])
        with mock.patch.object(dep, "_garantir_pip", return_value=True), \
             mock.patch.object(dep, "pasta_pacotes", return_value=Path("/nao/existe")), \
             mock.patch.object(dep, "_tem_internet", return_value=True), \
             mock.patch.object(dep, "_em_ambiente_virtual", return_value=False), \
             mock.patch.object(dep, "_pip", side_effect=lambda a: next(respostas)) as pip:
            dep.instalar([PACOTE])
        self.assertEqual(pip.call_args_list[1].args[0][0], "--user")


if __name__ == "__main__":
    unittest.main()
