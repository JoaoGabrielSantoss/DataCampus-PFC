import pytest
from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from django.test import override_settings

from .models import EventoAuditoria, Usuario

pytestmark = pytest.mark.django_db


def criar_usuario(email="joao@alunos.umc.br", perfil=Usuario.Perfil.PESQUISADOR):
    usuario = Usuario.objects.create_user(email, "João Teste", "Senha!2026x", perfil=perfil)
    agora = timezone.now()
    usuario.aceitou_politica_em = agora
    usuario.versao_politica = settings.LGPD_POLITICA_VERSAO
    usuario.aceitou_termos_em = agora
    usuario.versao_termos = settings.LGPD_TERMOS_VERSAO
    usuario.save(update_fields=["aceitou_politica_em", "versao_politica", "aceitou_termos_em", "versao_termos"])
    return usuario


def dados_cadastro(email="novo@alunos.umc.br"):
    return {
        "nome_completo": "Nova Pessoa",
        "email": email,
        "perfil": Usuario.Perfil.PESQUISADOR,
        "password1": "Senha!2026x",
        "password2": "Senha!2026x",
        "leu_politica": "on",
        "aceita_termos": "on",
    }


def test_cadastro_registra_aceites_e_restringe_dominio(client):
    resposta = client.post(reverse("cadastro"), dados_cadastro())
    assert resposta.status_code == 302
    usuario = Usuario.objects.get(email="novo@alunos.umc.br")
    assert usuario.aceitou_politica_em is not None
    assert usuario.versao_politica == settings.LGPD_POLITICA_VERSAO
    assert usuario.aceitou_termos_em is not None
    assert resposta.wsgi_request.user.is_authenticated

    client.logout()
    resposta = client.post(reverse("cadastro"), dados_cadastro("pessoa@gmail.com"))
    assert resposta.status_code == 200
    assert "@alunos.umc.br" in resposta.content.decode()
    assert not Usuario.objects.filter(email="pessoa@gmail.com").exists()


def test_login_com_email_e_senha(client):
    usuario = criar_usuario()
    resposta = client.post(reverse("login"), {"username": usuario.email, "password": "Senha!2026x"})
    assert resposta.status_code == 302
    assert resposta.wsgi_request.user.is_authenticated


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_redefinicao_de_senha_dispara_email_para_conta_cadastrada(client):
    usuario = criar_usuario()
    resposta = client.post(reverse("senha_reset"), {"email": usuario.email})
    assert resposta.status_code == 302
    assert resposta.url == reverse("senha_reset_done")
    assert len(mail.outbox) == 1
    assert usuario.email in mail.outbox[0].to


def test_documentos_legais_sao_publicos_e_aceite_atualiza_versoes(client):
    assert client.get(reverse("politica_privacidade")).status_code == 200
    assert client.get(reverse("termos_de_uso")).status_code == 200
    usuario = criar_usuario()
    usuario.versao_politica = "versao-antiga"
    usuario.versao_termos = "versao-antiga"
    usuario.save(update_fields=["versao_politica", "versao_termos"])
    client.force_login(usuario)

    bloqueio = client.get(reverse("inicio"))
    assert bloqueio.status_code == 302
    assert bloqueio.url == reverse("aceitar_documentos")
    aceite = client.post(reverse("aceitar_documentos"), {"leu_politica": "on", "aceita_termos": "on"})
    assert aceite.status_code == 302
    usuario.refresh_from_db()
    assert usuario.versao_politica == settings.LGPD_POLITICA_VERSAO
    assert usuario.versao_termos == settings.LGPD_TERMOS_VERSAO


def test_usuario_consulta_somente_a_propria_atividade(client):
    usuario = criar_usuario()
    EventoAuditoria.objects.create(usuario=usuario, tipo=EventoAuditoria.Tipo.LOGIN, rota="login", metodo="POST")
    client.force_login(usuario)
    resposta = client.get(reverse("minha_atividade"))
    assert resposta.status_code == 200
    assert len(resposta.context["eventos"]) >= 1


def test_exclusao_de_conta_exige_senha_e_confirmacao(client):
    usuario = criar_usuario()
    client.force_login(usuario)
    url = reverse("minha_conta")
    erro = client.post(url, {"senha_atual": "errada", "confirmacao": "EXCLUIR"})
    assert erro.status_code == 200
    assert Usuario.objects.filter(pk=usuario.pk).exists()

    sucesso = client.post(url, {"senha_atual": "Senha!2026x", "confirmacao": "EXCLUIR"})
    assert sucesso.status_code == 302
    assert not Usuario.objects.filter(pk=usuario.pk).exists()

