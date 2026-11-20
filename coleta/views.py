from django.contrib import messages
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.http import Http404
import logging
from django.shortcuts import get_object_or_404, redirect, render

from autenticacao.models import EventoAuditoria, Usuario
from autenticacao.permissoes import exige_perfil
from estudos.models import Estudo

from .forms import RegistroParticipacaoForm, ValoresColetaForm
from .models import DadoColetado, Participacao, Voluntario
from .servicos import (
    avaliar_estudo,
    dados_reutilizaveis,
    preparar_valor,
    valores_conhecidos,
    variaveis_pendentes,
)

logger = logging.getLogger(__name__)


def registrar_evento(usuario, tipo, objeto, campos=()):
    EventoAuditoria.objects.create(
        usuario=usuario,
        tipo=tipo,
        modelo_alvo=objeto._meta.label,
        id_alvo=str(objeto.pk),
        campos_alterados=list(campos),
    )


def informar(email, assunto, mensagem):
    if not email:
        return False
    try:
        return send_mail(assunto, mensagem, None, [email], fail_silently=False) == 1
    except Exception:
        # A falha da notificação não deve desfazer a coleta. O log registra o erro
        # sem incluir o endereço do destinatário nem o conteúdo da mensagem.
        logger.exception("Falha ao enviar uma notificação pelo Brevo.")
        return False


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def registrar(request):
    form = RegistroParticipacaoForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        estudo = form.cleaned_data["estudo"]
        with transaction.atomic():
            voluntario, novo, autorizacao_atualizada, nome_atualizado = Voluntario.registrar(
                form.cleaned_data["cpf"],
                nome=form.cleaned_data["nome"],
                autorizado_reuso=form.cleaned_data["autorizado_reuso"],
                usuario=request.user,
            )
            if novo:
                registrar_evento(request.user, EventoAuditoria.Tipo.CRIACAO, voluntario)
            elif autorizacao_atualizada or nome_atualizado:
                campos = []
                if nome_atualizado:
                    campos.append("nome_cifrado")
                if autorizacao_atualizada:
                    campos.append("autorizou_reuso_em")
                registrar_evento(
                    request.user,
                    EventoAuditoria.Tipo.ALTERACAO,
                    voluntario,
                    campos=campos,
                )
            participacao, criada = Participacao.objects.get_or_create(
                estudo=estudo,
                voluntario=voluntario,
                defaults={"profissional": request.user if request.user.e_profissional else None},
            )
            if not criada:
                messages.info(request, "Esse voluntário já está registrado neste estudo.")
                return redirect("coleta:participacao", id=participacao.pk)

            criterios = estudo.criterios.select_related("variavel").all()
            ids_variaveis = [criterio.variavel_id for criterio in criterios]
            participacao.dados_utilizados.add(*dados_reutilizaveis(voluntario, ids_variaveis))
            situacao, faltantes = avaliar_estudo(estudo, valores_conhecidos(participacao))
            participacao.situacao = situacao
            participacao.save(update_fields=["situacao", "atualizado_em"])
            registrar_evento(request.user, EventoAuditoria.Tipo.CRIACAO, participacao)
        if situacao == Participacao.Situacao.PENDENTE and faltantes:
            enviado = informar(
                request.user.email,
                "Pendência de coleta no DataCampus",
                f"Há dados pendentes para o paciente {voluntario.nome_publico} no estudo {estudo.nome}.",
            )
            if not enviado:
                messages.warning(request, "A participação foi registrada, mas o e-mail de aviso não foi enviado.")
            messages.success(request, "Participação registrada. Confira os dados que ainda precisam ser coletados.")
        elif situacao == Participacao.Situacao.ELEGIVEL:
            enviado = informar(
                estudo.pesquisador.email,
                "Coleta concluída no DataCampus",
                f"A coleta do paciente {voluntario.nome_publico} no estudo {estudo.nome} foi concluída.",
            )
            messages.success(request, "Participação registrada e coleta concluída.")
            if not enviado:
                messages.warning(request, "A coleta foi concluída, mas o e-mail de aviso ao pesquisador não foi enviado.")
        else:
            messages.success(request, "Participação registrada. A coleta foi encerrada para este estudo.")
        return redirect("coleta:participacao", id=participacao.pk)
    return render(request, "coleta/registro.html", {"form": form})


@exige_perfil(Usuario.Perfil.PROFISSIONAL, Usuario.Perfil.PESQUISADOR)
def participacao(request, id):
    participacoes = Participacao.objects.select_related("estudo", "voluntario", "profissional")
    if request.user.e_pesquisador:
        participacoes = participacoes.filter(estudo__pesquisador=request.user)
    else:
        participacoes = participacoes.filter(profissional=request.user)
    participacao = get_object_or_404(participacoes, pk=id)
    pendentes = variaveis_pendentes(participacao)
    valores = valores_conhecidos(participacao)
    encerrada_por_inelegibilidade = participacao.situacao == Participacao.Situacao.INELEGIVEL
    pode_coletar = request.user.e_profissional and not encerrada_por_inelegibilidade and bool(pendentes)
    if request.method == "POST" and not request.user.e_profissional:
        raise PermissionDenied

    # A coleta é sequencial para que o servidor possa encerrar o fluxo no
    # primeiro critério não atendido, sem gravar as respostas seguintes.
    variavel_atual = pendentes[0] if pode_coletar else None
    variaveis_formulario = [variavel_atual] if variavel_atual else []
    form = ValoresColetaForm(
        request.POST or None,
        variaveis=variaveis_formulario,
        valores=valores,
    )
    if pode_coletar:
        form.fields[ValoresColetaForm.chave(variavel_atual)].required = True

    if request.method == "POST" and pode_coletar and form.is_valid():
        with transaction.atomic():
            valor = form.cleaned_data[ValoresColetaForm.chave(variavel_atual)]
            dado = DadoColetado.objects.filter(
                voluntario=participacao.voluntario,
                variavel=variavel_atual,
                estudo_origem=participacao.estudo,
            ).first()
            if dado is None:
                dado = DadoColetado(
                    voluntario=participacao.voluntario,
                    variavel=variavel_atual,
                    coletado_por=request.user,
                    estudo_origem=participacao.estudo,
                )
            dado.definir_valor(preparar_valor(variavel_atual, valor))
            dado.coletado_por = request.user
            dado.estudo_origem = participacao.estudo
            dado.save()
            participacao.dados_utilizados.add(dado)
            registrar_evento(request.user, EventoAuditoria.Tipo.CRIACAO, dado)
            valores = valores_conhecidos(participacao)
            anterior = participacao.situacao
            situacao, faltantes = avaliar_estudo(participacao.estudo, valores)
            participacao.situacao = situacao
            participacao.save(update_fields=["situacao", "atualizado_em"])
            if anterior != situacao:
                registrar_evento(request.user, EventoAuditoria.Tipo.ALTERACAO, participacao)
        if situacao == Participacao.Situacao.ELEGIVEL:
            enviado = informar(
                participacao.estudo.pesquisador.email,
                "Coleta concluída no DataCampus",
                f"A coleta do paciente {participacao.voluntario.nome_publico} no estudo {participacao.estudo.nome} foi concluída.",
            )
            messages.success(request, "Dados salvos. A coleta deste estudo foi concluída.")
            if not enviado:
                messages.warning(request, "A coleta foi concluída, mas o e-mail de aviso ao pesquisador não foi enviado.")
        else:
            messages.success(request, "Dados salvos.")
        return redirect("coleta:participacao", id=participacao.pk)
    respondidos = participacao.estudo.criterios.count() - len(pendentes)
    return render(request, "coleta/participacao.html", {
        "participacao": participacao,
        "form": form,
        "pendentes": pendentes,
        "pode_coletar": pode_coletar,
        "encerrada_por_inelegibilidade": encerrada_por_inelegibilidade,
        "passo_atual": respondidos + 1,
        "total_criterios": participacao.estudo.criterios.count(),
        "situacao": participacao.situacao,
        "pesquisador": request.user.e_pesquisador,
    })


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def lista_pendencias(request):
    participacoes = Participacao.objects.filter(
        profissional=request.user,
        situacao=Participacao.Situacao.PENDENTE,
        estudo__situacao=Estudo.Situacao.ATIVO,
    ).select_related("estudo", "voluntario")
    return render(request, "coleta/pendencias.html", {"participacoes": participacoes})


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def painel_estudo(request, id):
    estudo = get_object_or_404(Estudo, pk=id, pesquisador=request.user)
    participacoes = estudo.participacoes.select_related("voluntario").order_by("situacao", "-atualizado_em")
    totais = {
        "total": participacoes.count(),
        "pendentes": participacoes.filter(situacao=Participacao.Situacao.PENDENTE).count(),
        "elegiveis": participacoes.filter(situacao=Participacao.Situacao.ELEGIVEL).count(),
        "inelegiveis": participacoes.filter(situacao=Participacao.Situacao.INELEGIVEL).count(),
    }
    return render(request, "coleta/painel_estudo.html", {"estudo": estudo, "participacoes": participacoes, "totais": totais})


def formatar_dado_voluntario(dado):
    valor = dado.obter_valor()
    variavel = dado.variavel
    if variavel.tipo in (variavel.Tipo.NOMINAL, variavel.Tipo.ORDINAL):
        try:
            opcao = variavel.dominio.opcoes.filter(pk=int(valor)).first() if variavel.dominio_id else None
        except (TypeError, ValueError):
            opcao = None
        valor = opcao.rotulo if opcao else "Resposta registrada"
    elif variavel.tipo == variavel.Tipo.BOOLEANA:
        valor = "Sim" if valor else "Não"
    elif variavel.tipo == variavel.Tipo.DATA:
        from datetime import date

        try:
            valor = date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
        except ValueError:
            pass
    if variavel.tipo == variavel.Tipo.NUMERICA and variavel.unidade:
        valor = f"{valor} {variavel.unidade}"
    return valor


@exige_perfil(Usuario.Perfil.PROFISSIONAL, Usuario.Perfil.PESQUISADOR)
def lista_voluntarios(request):
    if request.user.e_pesquisador:
        participacoes_visiveis = Participacao.objects.filter(estudo__pesquisador=request.user)
        voluntarios = Voluntario.objects.filter(
            participacoes__estudo__pesquisador=request.user
        ).distinct()
    else:
        participacoes_visiveis = Participacao.objects.filter(profissional=request.user)
        voluntarios = Voluntario.objects.filter(
            Q(criado_por=request.user) | Q(participacoes__profissional=request.user)
        ).distinct()

    registros = []
    for voluntario in voluntarios.order_by("-criado_em"):
        participacoes = list(
            participacoes_visiveis.filter(voluntario=voluntario)
            .select_related("estudo")
            .prefetch_related("dados_utilizados__variavel__dominio__opcoes")
            .order_by("-criado_em")
        )
        for participacao in participacoes:
            participacao.dados_exibidos = [
                {
                    "variavel": dado.variavel.nome,
                    "valor": formatar_dado_voluntario(dado),
                    "coletado_em": dado.coletado_em,
                }
                for dado in participacao.dados_utilizados.all()
            ]
        registros.append({"voluntario": voluntario, "participacoes": participacoes})

    return render(request, "coleta/voluntarios.html", {"registros": registros, "total": len(registros)})
