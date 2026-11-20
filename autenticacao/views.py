from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import CadastroForm, ExcluirContaForm, LoginForm
from .models import EventoAuditoria, Usuario
from .permissoes import exige_perfil


class EntrarView(LoginView):
    authentication_form = LoginForm
    template_name = "autenticacao/login.html"
    redirect_authenticated_user = True


def cadastrar(request):
    if request.user.is_authenticated:
        return redirect("inicio")

    form = CadastroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save(commit=False)
        agora = timezone.now()
        usuario.aceitou_politica_em = agora
        usuario.versao_politica = settings.LGPD_POLITICA_VERSAO
        usuario.aceitou_termos_em = agora
        usuario.versao_termos = settings.LGPD_TERMOS_VERSAO
        usuario.save()
        login(request, usuario)
        return redirect("inicio")
    return render(request, "autenticacao/cadastro.html", {"form": form})


@login_required
def inicio(request):
    return render(request, "autenticacao/inicio.html")


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def coleta(request):
    from coleta.views import registrar

    return registrar(request)


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def pendencias(request):
    from coleta.views import lista_pendencias

    return lista_pendencias(request)


def politica_privacidade(request):
    return render(request, "autenticacao/politica_privacidade.html", {
        "versao_politica": settings.LGPD_POLITICA_VERSAO,
        "controlador_nome": settings.LGPD_CONTROLADOR_NOME,
        "contato_lgpd": settings.LGPD_CONTATO,
        "encarregado_lgpd": settings.LGPD_ENCARREGADO,
    })


def termos_de_uso(request):
    return render(request, "autenticacao/termos_de_uso.html", {
        "versao_termos": settings.LGPD_TERMOS_VERSAO,
        "controlador_nome": settings.LGPD_CONTROLADOR_NOME,
        "contato_lgpd": settings.LGPD_CONTATO,
    })


@login_required
def aceitar_documentos(request):
    if request.method == "POST" and request.POST.get("leu_politica") == "on" and request.POST.get("aceita_termos") == "on":
        agora = timezone.now()
        request.user.aceitou_politica_em = agora
        request.user.versao_politica = settings.LGPD_POLITICA_VERSAO
        request.user.aceitou_termos_em = agora
        request.user.versao_termos = settings.LGPD_TERMOS_VERSAO
        request.user.save(update_fields=[
            "aceitou_politica_em", "versao_politica", "aceitou_termos_em", "versao_termos",
        ])
        messages.success(request, "Confirmação registrada.")
        return redirect("inicio")
    return render(request, "autenticacao/aceitar_documentos.html")


@login_required
def minha_atividade(request):
    eventos = EventoAuditoria.objects.filter(usuario=request.user).order_by("-criado_em")[:100]
    return render(request, "autenticacao/minha_atividade.html", {"eventos": eventos})


@login_required
def minha_conta(request):
    usuario = request.user
    estudos_vinculados = usuario.estudos.count() if usuario.e_pesquisador else 0
    form = ExcluirContaForm(
        usuario=usuario,
        data=request.POST if request.method == "POST" else None,
    )

    if request.method == "POST":
        if estudos_vinculados:
            messages.error(
                request,
                "Esta conta ainda é responsável por estudos. Peça ao administrador para transferir "
                "a responsabilidade antes de excluir a conta.",
            )
        elif form.is_valid():
            # Registrar logout enquanto a conta ainda existe; depois, remover a conta.
            logout(request)
            usuario.delete()
            messages.success(request, "Sua conta foi excluída.")
            return redirect("login")

    return render(request, "autenticacao/minha_conta.html", {
        "form": form,
        "estudos_vinculados": estudos_vinculados,
    })
