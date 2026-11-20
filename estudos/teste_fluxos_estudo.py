import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from autenticacao.models import Usuario
from catalogo.models import Categoria, Operador, Subcategoria, Variavel

from .models import Criterio, Estudo

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexto(client):
    pesquisador = Usuario.objects.create_user(
        "pesquisador@fluxo.umc.br", "Pesquisador Fluxo", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )
    agora = timezone.now()
    pesquisador.aceitou_politica_em = agora
    pesquisador.versao_politica = settings.LGPD_POLITICA_VERSAO
    pesquisador.aceitou_termos_em = agora
    pesquisador.versao_termos = settings.LGPD_TERMOS_VERSAO
    pesquisador.save(update_fields=["aceitou_politica_em", "versao_politica", "aceitou_termos_em", "versao_termos"])
    client.force_login(pesquisador)
    categoria = Categoria.objects.create(codigo="FLX", nome="Fluxo de teste", ordem=999)
    subcategoria = Subcategoria.objects.create(categoria=categoria, codigo="EST", nome="Estudos", ordem=1)
    variavel = Variavel.objects.create(
        subcategoria=subcategoria,
        codigo="altura_fluxo",
        nome="Altura para teste",
        tipo=Variavel.Tipo.NUMERICA,
        unidade="cm",
        minimo=30,
        maximo=250,
    )
    return client, pesquisador, categoria, subcategoria, variavel


def criar_estudo(pesquisador, nome="Estudo de fluxo"):
    return Estudo.objects.create(
        nome=nome,
        condicao="Condição de teste",
        situacao=Estudo.Situacao.ATIVO,
        pesquisador=pesquisador,
    )


def test_pesquisador_cria_edita_e_consulta_proprio_estudo(contexto):
    client, pesquisador, categoria, subcategoria, variavel = contexto
    resposta = client.post(reverse("estudos:criar"), {
        "nome": "Pesquisa criada pelo formulário",
        "condicao": "Condição clínica",
        "descricao": "Descrição do estudo",
        "participantes_necessarios": "12",
        "situacao": Estudo.Situacao.ATIVO,
    })
    estudo = Estudo.objects.get(nome="Pesquisa criada pelo formulário")
    assert resposta.status_code == 302
    assert estudo.pesquisador == pesquisador

    resposta = client.post(reverse("estudos:editar", args=[estudo.pk]), {
        "nome": "Pesquisa atualizada",
        "condicao": "Condição clínica",
        "descricao": "Descrição revisada",
        "participantes_necessarios": "15",
        "situacao": Estudo.Situacao.ATIVO,
    })
    estudo.refresh_from_db()
    assert resposta.status_code == 302
    assert estudo.nome == "Pesquisa atualizada"
    assert client.get(reverse("estudos:detalhe", args=[estudo.pk])).status_code == 200

    outro = Usuario.objects.create_user("outro@fluxo.umc.br", "Outro Pesquisador", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR)
    agora = timezone.now()
    outro.aceitou_politica_em = agora
    outro.versao_politica = settings.LGPD_POLITICA_VERSAO
    outro.aceitou_termos_em = agora
    outro.versao_termos = settings.LGPD_TERMOS_VERSAO
    outro.save(update_fields=["aceitou_politica_em", "versao_politica", "aceitou_termos_em", "versao_termos"])
    client.force_login(outro)
    assert client.get(reverse("estudos:detalhe", args=[estudo.pk])).status_code == 404


def test_pesquisador_adiciona_e_remove_criterio(contexto):
    client, pesquisador, categoria, subcategoria, variavel = contexto
    estudo = criar_estudo(pesquisador)
    url = reverse("estudos:criar_criterio", args=[estudo.pk, variavel.pk])
    resposta = client.post(url, {"operador": Operador.MAIOR_IGUAL, "valor_numero": "100"})
    criterio = Criterio.objects.get(estudo=estudo)
    assert resposta.status_code == 302
    assert criterio.valor_numero == 100

    resposta = client.post(reverse("estudos:remover_criterio", args=[estudo.pk, criterio.pk]))
    assert resposta.status_code == 302
    assert not Criterio.objects.filter(pk=criterio.pk).exists()


def test_proposta_de_variavel_cria_item_no_catalogo(contexto):
    client, pesquisador, categoria, subcategoria, variavel = contexto
    estudo = criar_estudo(pesquisador)
    resposta = client.post(reverse("estudos:propor_variavel", args=[estudo.pk]), {
        "subcategoria": subcategoria.pk,
        "nome": "Temperatura experimental inédita",
        "tipo": Variavel.Tipo.NUMERICA,
        "unidade": "graus",
        "minimo": "0",
        "maximo": "50",
        "sensivel": "on",
        "confirmar": "1",
    })
    proposta = Variavel.objects.get(nome="Temperatura experimental inédita")
    assert resposta.status_code == 302
    assert proposta.codigo == "temperatura_experimental_inedita"
    assert proposta.sensivel


def test_lista_de_estudos_tem_indicadores_calculados(contexto):
    client, pesquisador, categoria, subcategoria, variavel = contexto
    criar_estudo(pesquisador, "Estudo ativo")
    Estudo.objects.create(
        nome="Estudo rascunho",
        condicao="Condição de teste",
        situacao=Estudo.Situacao.RASCUNHO,
        pesquisador=pesquisador,
    )
    resposta = client.get(reverse("estudos:listar"))
    assert resposta.status_code == 200
    assert resposta.context["total_estudos"] == 2
    assert resposta.context["total_ativos"] == 1
    assert resposta.context["total_rascunhos"] == 1

