from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save, m2m_changed
from django.dispatch import receiver

from catalogo.models import Variavel
from estudos.models import Criterio, Estudo

from .auditoria import registrar_evento
from .models import EventoAuditoria, Usuario


MODELOS_AUDITADOS = (Usuario, Estudo, Criterio, Variavel)


def _campos_persistidos(modelo):
    return [
        campo for campo in modelo._meta.concrete_fields
        if not campo.primary_key and not campo.auto_created and campo.name != "password"
    ]


def _capturar_estado_anterior(sender, instance, raw=False, **kwargs):
    if raw or not instance.pk:
        instance._auditoria_campos_alterados = []
        return
    anterior = sender._base_manager.filter(pk=instance.pk).values().first()
    if anterior is None:
        instance._auditoria_campos_alterados = []
        return
    alterados = []
    for campo in _campos_persistidos(sender):
        if anterior.get(campo.attname) != getattr(instance, campo.attname):
            alterados.append(campo.name)
    instance._auditoria_campos_alterados = alterados


def _registrar_salvamento(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    campos = (
        [campo.name for campo in _campos_persistidos(sender)]
        if created
        else getattr(instance, "_auditoria_campos_alterados", [])
    )
    if not created and not campos:
        return
    registrar_evento(
        EventoAuditoria.Tipo.CRIACAO if created else EventoAuditoria.Tipo.ALTERACAO,
        modelo_alvo=sender._meta.label_lower,
        id_alvo=instance.pk,
        campos_alterados=campos,
    )


def _registrar_exclusao(sender, instance, **kwargs):
    registrar_evento(
        EventoAuditoria.Tipo.EXCLUSAO,
        modelo_alvo=sender._meta.label_lower,
        id_alvo=instance.pk,
    )


for modelo in MODELOS_AUDITADOS:
    pre_save.connect(_capturar_estado_anterior, sender=modelo, dispatch_uid=f"auditoria-pre-{modelo._meta.label_lower}")
    post_save.connect(_registrar_salvamento, sender=modelo, dispatch_uid=f"auditoria-save-{modelo._meta.label_lower}")
    post_delete.connect(_registrar_exclusao, sender=modelo, dispatch_uid=f"auditoria-delete-{modelo._meta.label_lower}")


@receiver(m2m_changed, sender=Criterio.opcoes.through, dispatch_uid="auditoria-criterio-opcoes")
def registrar_opcoes_criterio(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        registrar_evento(
            EventoAuditoria.Tipo.ALTERACAO,
            modelo_alvo="estudos.criterio",
            id_alvo=instance.pk,
            campos_alterados=["opcoes"],
        )


@receiver(user_logged_in, dispatch_uid="auditoria-login")
def registrar_login(sender, request, user, **kwargs):
    registrar_evento(EventoAuditoria.Tipo.LOGIN, usuario=user, request=request)


@receiver(user_logged_out, dispatch_uid="auditoria-logout")
def registrar_logout(sender, request, user, **kwargs):
    registrar_evento(EventoAuditoria.Tipo.LOGOUT, usuario=user, request=request)


@receiver(user_login_failed, dispatch_uid="auditoria-login-falhou")
def registrar_login_falhou(sender, credentials, request, **kwargs):
    # Deliberadamente não lemos nem armazenamos o dicionário credentials.
    registrar_evento(EventoAuditoria.Tipo.LOGIN_FALHOU, request=request)
