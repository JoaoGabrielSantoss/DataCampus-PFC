from unittest.mock import patch

import pytest
from django.utils import timezone

from autenticacao.models import Usuario
from catalogo.models import Categoria, Operador, Subcategoria, Variavel
from estudos.models import Criterio, Estudo

from .models import DadoColetado, Participacao, Voluntario
from .seguranca import cifrar
from .servicos import avaliar_estudo, dados_reutilizaveis
from .views import informar

pytestmark = pytest.mark.django_db


def criar_base():
    pesquisador = Usuario.objects.create_user(
        "pesquisador@teste.umc.br", "Pesquisador Teste", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )
    categoria = Categoria.objects.create(codigo="TST", nome="Teste", ordem=999)
    subcategoria = Subcategoria.objects.create(categoria=categoria, codigo="TST", nome="Teste", ordem=1)
    variavel = Variavel.objects.create(
        subcategoria=subcategoria,
        codigo="idade_teste",
        nome="Idade de teste",
        tipo=Variavel.Tipo.NUMERICA,
    )
    return pesquisador, variavel


def criar_estudo(pesquisador, nome, situacao=Estudo.Situacao.ATIVO):
    return Estudo.objects.create(
        nome=nome,
        condicao="Condição de teste",
        situacao=situacao,
        pesquisador=pesquisador,
    )


def test_regra_elegibilidade_pendente_elegivel_inelegivel():
    pesquisador, variavel = criar_base()
    estudo = criar_estudo(pesquisador, "Estudo de elegibilidade")
    Criterio.objects.create(
        estudo=estudo,
        variavel=variavel,
        operador=Operador.MAIOR_IGUAL,
        valor_numero=18,
    )

    situacao, faltantes = avaliar_estudo(estudo, {})
    assert situacao == Participacao.Situacao.PENDENTE
    assert faltantes == [variavel]

    situacao, faltantes = avaliar_estudo(estudo, {variavel.pk: 20})
    assert situacao == Participacao.Situacao.ELEGIVEL
    assert faltantes == []

    situacao, _ = avaliar_estudo(estudo, {variavel.pk: 17})
    assert situacao == Participacao.Situacao.INELEGIVEL


def test_regra_reuso_exige_autorizacao_registrada():
    pesquisador, variavel = criar_base()
    voluntario = Voluntario.objects.create(
        identificador="hmac-de-teste",
        cpf_cifrado=cifrar("52998224725"),
    )
    dado = DadoColetado(
        voluntario=voluntario,
        variavel=variavel,
        estudo_origem=criar_estudo(pesquisador, "Origem"),
    )
    dado.definir_valor(20)
    dado.save()

    assert not dados_reutilizaveis(voluntario, [variavel.pk]).exists()
    voluntario.autorizou_reuso_em = timezone.now()
    voluntario.save(update_fields=["autorizou_reuso_em"])
    assert list(dados_reutilizaveis(voluntario, [variavel.pk])) == [dado]


def test_regra_descarte_preserva_reuso_ativo_e_apaga_apos_ultimo_uso():
    pesquisador, variavel = criar_base()
    origem = criar_estudo(pesquisador, "Origem")
    estudo_reuso = criar_estudo(pesquisador, "Estudo que reutiliza")
    outro_estudo_ativo = criar_estudo(pesquisador, "Outro estudo ativo")
    voluntario = Voluntario.objects.create(
        identificador="hmac-de-teste",
        cpf_cifrado=cifrar("52998224725"),
    )
    participacao_origem = Participacao.objects.create(estudo=origem, voluntario=voluntario)
    participacao_reuso = Participacao.objects.create(estudo=estudo_reuso, voluntario=voluntario)
    Participacao.objects.create(estudo=outro_estudo_ativo, voluntario=voluntario)
    dado = DadoColetado(voluntario=voluntario, variavel=variavel, estudo_origem=origem)
    dado.definir_valor(20)
    dado.save()
    participacao_origem.dados_utilizados.add(dado)
    participacao_reuso.dados_utilizados.add(dado)

    origem.situacao = Estudo.Situacao.ENCERRADO
    origem.save(update_fields=["situacao"])
    assert DadoColetado.objects.filter(pk=dado.pk).exists()

    estudo_reuso.situacao = Estudo.Situacao.ENCERRADO
    estudo_reuso.save(update_fields=["situacao"])
    assert not DadoColetado.objects.filter(pk=dado.pk).exists()
    assert Voluntario.objects.filter(pk=voluntario.pk).exists()


def test_falha_no_email_retorna_erro_sem_interromper_fluxo():
    with patch("coleta.views.send_mail", side_effect=RuntimeError("falha simulada")):
        assert informar("destino@teste.umc.br", "Assunto", "Mensagem") is False
