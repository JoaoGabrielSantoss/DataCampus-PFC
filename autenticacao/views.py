from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from datetime import timedelta
from django.db.models import Count
from django.db.models.functions import TruncMonth
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
    from coleta.models import Participacao
    from estudos.models import Estudo

    periodos = {"90": (90, "Últimos 90 dias"), "180": (180, "Últimos 6 meses"), "365": (365, "Último ano"), "todos": (None, "Todo o período")}
    periodo = request.GET.get("periodo", "180")
    if periodo not in periodos:
        periodo = "180"
    dias, periodo_legenda = periodos[periodo]
    hoje = timezone.localdate()
    data_inicial = hoje - timedelta(days=dias - 1) if dias else None
    inicio_grafico = hoje - timedelta(days=364)

    if request.user.e_pesquisador:
        estudos = Estudo.objects.filter(pesquisador=request.user)
        participacoes = Participacao.objects.filter(estudo__pesquisador=request.user)
    else:
        estudos = Estudo.objects.filter(participacoes__profissional=request.user).distinct()
        participacoes = Participacao.objects.filter(profissional=request.user)

    estudo_selecionado = request.GET.get("estudo", "")
    if estudo_selecionado:
        try:
            estudo_selecionado = str(estudos.get(pk=int(estudo_selecionado)).pk)
            participacoes = participacoes.filter(estudo_id=estudo_selecionado)
        except (Estudo.DoesNotExist, TypeError, ValueError):
            estudo_selecionado = ""

    if data_inicial:
        participacoes = participacoes.filter(criado_em__date__gte=data_inicial)
    situacao = request.GET.get("situacao", "")
    situacoes_validas = {choice for choice, _ in Participacao.Situacao.choices}
    if situacao not in situacoes_validas:
        situacao = ""

    totais_situacao = [
        {"key": valor, "label": rotulo, "total": participacoes.filter(situacao=valor).count()}
        for valor, rotulo in Participacao.Situacao.choices
    ]
    participacoes_filtradas = participacoes.filter(situacao=situacao) if situacao else participacoes
    total_participacoes = participacoes_filtradas.count()
    total_voluntarios = participacoes_filtradas.values("voluntario_id").distinct().count()

    mensal = {
        row["mes"].strftime("%Y-%m"): row["total"]
        for row in participacoes.filter(criado_em__date__gte=inicio_grafico).annotate(mes=TruncMonth("criado_em"))
        .values("mes").annotate(total=Count("pk")).order_by("mes")
    }
    nomes_meses = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
    cursor = (data_inicial or inicio_grafico).replace(day=1)
    primeiro_mes_atual = hoje.replace(day=1)
    meses = []
    while cursor <= primeiro_mes_atual:
        chave = cursor.strftime("%Y-%m")
        meses.append({"label": f"{nomes_meses[cursor.month - 1]}/{str(cursor.year)[-2:]}", "total": mensal.get(chave, 0)})
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

    por_estudo = list(
        participacoes.values("estudo_id", "estudo__nome")
        .annotate(total=Count("pk"))
        .order_by("-total", "estudo__nome")[:8]
    )
    recentes = participacoes_filtradas.select_related("estudo", "voluntario").order_by("-criado_em")[:8]
    total_estudos = estudos.count()
    estudos_ativos = estudos.filter(situacao=Estudo.Situacao.ATIVO).count()
    chart_data = {
        "situacoes": totais_situacao,
        "meses": meses,
        "estudos": [{"id": row["estudo_id"], "nome": row["estudo__nome"], "total": row["total"]} for row in por_estudo],
    }

    return render(request, "autenticacao/inicio.html", {
        "is_pesquisador": request.user.e_pesquisador,
        "periodos": [(key, label) for key, (_, label) in periodos.items()],
        "periodo": periodo,
        "periodo_legenda": periodo_legenda,
        "estudos": estudos.order_by("nome"),
        "estudo_selecionado": estudo_selecionado,
        "situacao_selecionada": situacao,
        "situacoes": Participacao.Situacao.choices,
        "total_estudos": total_estudos,
        "estudos_ativos": estudos_ativos,
        "total_participacoes": total_participacoes,
        "total_voluntarios": total_voluntarios,
        "pendentes": participacoes.filter(situacao=Participacao.Situacao.PENDENTE).count(),
        "elegiveis": participacoes.filter(situacao=Participacao.Situacao.ELEGIVEL).count(),
        "inelegiveis": participacoes.filter(situacao=Participacao.Situacao.INELEGIVEL).count(),
        "recentes": recentes,
        "chart_data": chart_data,
    })


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
