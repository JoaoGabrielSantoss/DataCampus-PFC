from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from autenticacao.models import EventoAuditoria, Usuario
from catalogo.models import Categoria, Operador, Subcategoria, Variavel
from estudos.models import Criterio, Estudo

from .forms import RegistroParticipacaoForm, ValoresColetaForm
from .models import DadoColetado, Participacao, Voluntario
from .seguranca import cifrar, decifrar, identificador_cpf, validar_cpf

pytestmark = pytest.mark.django_db


def criar_usuario(email, perfil):
    usuario = Usuario.objects.create_user(email, "Pessoa de Teste", "Senha!2026x", perfil=perfil)
    agora = timezone.now()
    usuario.aceitou_politica_em = agora
    usuario.versao_politica = settings.LGPD_POLITICA_VERSAO
    usuario.aceitou_termos_em = agora
    usuario.versao_termos = settings.LGPD_TERMOS_VERSAO
    usuario.save(update_fields=["aceitou_politica_em", "versao_politica", "aceitou_termos_em", "versao_termos"])
    return usuario


@pytest.fixture
def base_coleta():
    pesquisador = criar_usuario("pesquisador@teste.umc.br", Usuario.Perfil.PESQUISADOR)
    profissional = criar_usuario("profissional@teste.umc.br", Usuario.Perfil.PROFISSIONAL)
    categoria = Categoria.objects.create(codigo="TST", nome="Teste", ordem=999)
    subcategoria = Subcategoria.objects.create(categoria=categoria, codigo="COL", nome="Coleta", ordem=1)
    idade = Variavel.objects.create(
        subcategoria=subcategoria,
        codigo="idade_teste",
        nome="Idade",
        tipo=Variavel.Tipo.NUMERICA,
        unidade="anos",
        minimo=0,
        maximo=120,
    )
    peso = Variavel.objects.create(
        subcategoria=subcategoria,
        codigo="peso_teste",
        nome="Peso",
        tipo=Variavel.Tipo.NUMERICA,
        unidade="kg",
        minimo=1,
        maximo=300,
    )
    estudo = Estudo.objects.create(
        nome="Estudo de teste",
        condicao="Condição de teste",
        situacao=Estudo.Situacao.ATIVO,
        pesquisador=pesquisador,
    )
    Criterio.objects.create(estudo=estudo, variavel=idade, operador=Operador.MAIOR_IGUAL, valor_numero=18)
    Criterio.objects.create(estudo=estudo, variavel=peso, operador=Operador.MAIOR_IGUAL, valor_numero=40)
    return pesquisador, profissional, estudo, idade, peso


def test_cpf_e_dados_sao_protegidos():
    assert validar_cpf("529.982.247-25") == "52998224725"
    assert len(identificador_cpf("52998224725")) == 64
    with pytest.raises(ValidationError):
        validar_cpf("11111111111")
    texto_cifrado = cifrar("resposta sensível")
    assert texto_cifrado != "resposta sensível"
    assert decifrar(texto_cifrado) == "resposta sensível"


def test_formulario_de_registro_restringe_estudo_e_valida_cpf(base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    form = RegistroParticipacaoForm(
        {"estudo": estudo.pk, "nome": "  Maria   Teste ", "cpf": "529.982.247-25"},
        usuario=profissional,
    )
    assert form.is_valid()
    assert form.cleaned_data["nome"] == "Maria Teste"

    invalido = RegistroParticipacaoForm(
        {"estudo": estudo.pk, "nome": "Maria Teste", "cpf": "111.111.111-11"},
        usuario=profissional,
    )
    assert not invalido.is_valid()
    assert "cpf" in invalido.errors


@patch("coleta.views.send_mail", return_value=1)
def test_registro_cria_participacao_e_notifica_pendencia(mock_email, client, base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    client.force_login(profissional)
    resposta = client.post(reverse("coleta:coleta"), {
        "estudo": estudo.pk,
        "nome": "Maria Voluntária",
        "cpf": "52998224725",
    })

    assert resposta.status_code == 302
    voluntario = Voluntario.objects.get()
    participacao = Participacao.objects.get()
    assert voluntario.nome_publico == "Maria Voluntária"
    assert voluntario.nome_cifrado != "Maria Voluntária"
    assert voluntario.cpf_mascarado.endswith("-25")
    assert participacao.situacao == Participacao.Situacao.PENDENTE
    mock_email.assert_called_once()
    assert mock_email.call_args.args[3] == [profissional.email]


@patch("coleta.views.send_mail", return_value=1)
def test_coleta_e_sequencial_e_para_ao_reprovar_criterio(mock_email, client, base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    voluntario = Voluntario.registrar(
        "52998224725", nome="Maria Voluntária", autorizado_reuso=False, usuario=profissional
    )[0]
    participacao = Participacao.objects.create(estudo=estudo, voluntario=voluntario, profissional=profissional)
    client.force_login(profissional)
    url = reverse("coleta:participacao", args=[participacao.pk])

    tela_inicial = client.get(url).content.decode()
    assert f'name="variavel_{idade.pk}"' in tela_inicial
    assert f'name="variavel_{peso.pk}"' not in tela_inicial

    resposta = client.post(url, {f"variavel_{idade.pk}": "17", f"variavel_{peso.pk}": "90"})
    participacao.refresh_from_db()
    assert resposta.status_code == 302
    assert participacao.situacao == Participacao.Situacao.INELEGIVEL
    assert list(participacao.dados_utilizados.values_list("variavel_id", flat=True)) == [idade.pk]
    assert peso.pk not in list(DadoColetado.objects.values_list("variavel_id", flat=True))
    assert "encerrada" in client.get(url).content.decode().lower()
    mock_email.assert_not_called()


@patch("coleta.views.send_mail", return_value=1)
def test_coleta_aprova_um_campo_por_vez_e_avisa_pesquisador(mock_email, client, base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    voluntario = Voluntario.registrar(
        "52998224725", nome="Maria Voluntária", autorizado_reuso=False, usuario=profissional
    )[0]
    participacao = Participacao.objects.create(estudo=estudo, voluntario=voluntario, profissional=profissional)
    client.force_login(profissional)
    url = reverse("coleta:participacao", args=[participacao.pk])

    resposta = client.post(url, {f"variavel_{idade.pk}": "25"})
    participacao.refresh_from_db()
    assert resposta.status_code == 302
    assert participacao.situacao == Participacao.Situacao.PENDENTE
    assert list(participacao.dados_utilizados.values_list("variavel_id", flat=True)) == [idade.pk]

    tela_peso = client.get(url).content.decode()
    assert f'name="variavel_{peso.pk}"' in tela_peso
    assert f'name="variavel_{idade.pk}"' not in tela_peso
    resposta = client.post(url, {f"variavel_{peso.pk}": "65"})
    participacao.refresh_from_db()
    assert resposta.status_code == 302
    assert participacao.situacao == Participacao.Situacao.ELEGIVEL
    assert mock_email.call_count == 1
    assert mock_email.call_args.args[3] == [pesquisador.email]

    # Reenvio do POST não cria outro dado nem dispara outra notificação.
    client.post(url, {f"variavel_{peso.pk}": "65"})
    assert mock_email.call_count == 1
    assert DadoColetado.objects.count() == 2


@patch("coleta.views.send_mail", return_value=1)
def test_dado_reutilizado_e_classificado_antes_de_iniciar_nova_coleta(mock_email, client, base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    voluntario = Voluntario.registrar(
        "52998224725", nome="Maria Voluntária", autorizado_reuso=True, usuario=profissional
    )[0]
    dado = DadoColetado(
        voluntario=voluntario,
        variavel=idade,
        estudo_origem=estudo,
        coletado_por=profissional,
    )
    dado.definir_valor("16")
    dado.save()
    outro_estudo = Estudo.objects.create(
        nome="Estudo de reaproveitamento",
        condicao="Condição de teste",
        situacao=Estudo.Situacao.ATIVO,
        pesquisador=pesquisador,
    )
    Criterio.objects.create(
        estudo=outro_estudo,
        variavel=idade,
        operador=Operador.MAIOR_IGUAL,
        valor_numero=18,
    )
    client.force_login(profissional)

    resposta = client.post(reverse("coleta:coleta"), {
        "estudo": outro_estudo.pk,
        "nome": "Maria Voluntária",
        "cpf": "52998224725",
        "autorizado_reuso": "on",
    })

    participacao = Participacao.objects.get(estudo=outro_estudo)
    assert resposta.status_code == 302
    assert participacao.situacao == Participacao.Situacao.INELEGIVEL
    assert list(participacao.dados_utilizados.all()) == [dado]
    mock_email.assert_not_called()


def test_pesquisador_nao_pode_enviar_respostas_da_coleta(client, base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    voluntario = Voluntario.registrar(
        "52998224725", nome="Maria Voluntária", autorizado_reuso=False, usuario=profissional
    )[0]
    participacao = Participacao.objects.create(estudo=estudo, voluntario=voluntario, profissional=profissional)
    client.force_login(pesquisador)

    assert client.get(reverse("coleta:participacao", args=[participacao.pk])).status_code == 200
    resposta = client.post(reverse("coleta:participacao", args=[participacao.pk]), {f"variavel_{idade.pk}": "25"})
    assert resposta.status_code == 403
    assert DadoColetado.objects.count() == 0


def test_painel_estudo_exibe_indicadores_e_esconde_estudo_de_outra_pessoa(client, base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    client.force_login(pesquisador)
    resposta = client.get(reverse("coleta:painel_estudo", args=[estudo.pk]))
    assert resposta.status_code == 200
    assert resposta.context["totais"] == {"total": 0, "pendentes": 0, "elegiveis": 0, "inelegiveis": 0}

    outra = criar_usuario("outra@teste.umc.br", Usuario.Perfil.PESQUISADOR)
    client.force_login(outra)
    assert client.get(reverse("coleta:painel_estudo", args=[estudo.pk])).status_code == 404


def test_lista_de_pendencias_e_voluntarios_respeita_profissional(client, base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    voluntario = Voluntario.registrar(
        "52998224725", nome="Maria Voluntária", autorizado_reuso=False, usuario=profissional
    )[0]
    participacao = Participacao.objects.create(estudo=estudo, voluntario=voluntario, profissional=profissional)
    client.force_login(profissional)

    pendencias = client.get(reverse("coleta:pendencias"))
    assert pendencias.status_code == 200
    assert "Maria Voluntária" in pendencias.content.decode()
    voluntarios = client.get(reverse("coleta:lista_voluntarios"))
    assert voluntarios.status_code == 200
    assert "Maria Voluntária" in voluntarios.content.decode()
    assert "***.***.***-25" in voluntarios.content.decode()


def test_formulario_de_valores_aplica_limites_da_variavel(base_coleta):
    pesquisador, profissional, estudo, idade, peso = base_coleta
    form = ValoresColetaForm({f"variavel_{idade.pk}": "121"}, variaveis=[idade])
    assert not form.is_valid()
    assert f"variavel_{idade.pk}" in form.errors
