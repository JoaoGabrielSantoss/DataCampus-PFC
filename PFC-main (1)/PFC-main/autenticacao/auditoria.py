from contextvars import ContextVar

from .models import EventoAuditoria


_requisicao_atual = ContextVar("requisicao_auditoria", default=None)


def registrar_evento(tipo, *, usuario=None, request=None, rota="", metodo="", status_http=None,
                    modelo_alvo="", id_alvo="", campos_alterados=None):
    """Registra apenas metadados; nunca recebe corpo, senha, IP ou valores dos campos."""
    requisicao = request or _requisicao_atual.get()
    if requisicao is not None:
        if usuario is None:
            usuario = getattr(requisicao, "user", None)
        if not rota:
            rota = requisicao.path_info
        if not metodo:
            metodo = requisicao.method

    if not getattr(usuario, "is_authenticated", False):
        usuario = None

    EventoAuditoria.objects.create(
        usuario=usuario,
        tipo=tipo,
        rota=(rota or "")[:255],
        metodo=(metodo or "")[:10],
        status_http=status_http,
        modelo_alvo=(modelo_alvo or "")[:100],
        id_alvo=str(id_alvo or "")[:80],
        campos_alterados=sorted(set(campos_alterados or [])),
    )
