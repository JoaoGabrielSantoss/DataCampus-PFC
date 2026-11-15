from django.db.models.signals import post_delete, pre_save, post_save
from django.dispatch import receiver

from estudos.models import Estudo
from autenticacao.models import EventoAuditoria

from .models import DadoColetado, Participacao, Voluntario


@receiver(post_delete, sender=Voluntario)
@receiver(post_delete, sender=DadoColetado)
@receiver(post_delete, sender=Participacao)
def registrar_exclusao(sender, instance, **kwargs):
    EventoAuditoria.objects.create(
        usuario=None,
        tipo=EventoAuditoria.Tipo.EXCLUSAO,
        modelo_alvo=instance._meta.label,
        id_alvo=str(instance.pk),
        campos_alterados=[],
    )


@receiver(pre_save, sender=Estudo)
def guardar_situacao_anterior(sender, instance, **kwargs):
    instance._situacao_anterior = None
    if instance.pk:
        instance._situacao_anterior = sender.objects.filter(pk=instance.pk).values_list("situacao", flat=True).first()


@receiver(post_save, sender=Estudo)
def descartar_dados_ao_encerrar(sender, instance, **kwargs):
    if (
        instance.situacao != Estudo.Situacao.ENCERRADO
        or getattr(instance, "_situacao_anterior", None) == Estudo.Situacao.ENCERRADO
    ):
        return
    ids_voluntarios = list(instance.participacoes.values_list("voluntario_id", flat=True))
    instance.participacoes.all().delete()
    # Remover todos os dados dos voluntários vinculados ao estudo encerrado que
    # já não sejam usados por nenhuma participação ativa. Isso também limpa dados
    # originados em outro estudo cujo último uso acabou agora.
    ids_dados = DadoColetado.objects.filter(voluntario_id__in=ids_voluntarios).values_list("pk", flat=True)
    dados_reutilizados_ativos = Participacao.objects.filter(
        estudo__situacao=Estudo.Situacao.ATIVO,
        voluntario_id__in=ids_voluntarios,
        dados_utilizados__in=ids_dados,
    ).values_list("dados_utilizados__pk", flat=True)
    DadoColetado.objects.filter(pk__in=ids_dados).exclude(pk__in=dados_reutilizados_ativos).delete()
    ativos = Participacao.objects.filter(
        voluntario_id__in=ids_voluntarios,
        estudo__situacao=Estudo.Situacao.ATIVO,
    ).values_list("voluntario_id", flat=True)
    Voluntario.objects.filter(pk__in=ids_voluntarios).exclude(pk__in=ativos).delete()
