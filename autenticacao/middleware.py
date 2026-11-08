from django.conf import settings
from django.shortcuts import redirect

from .auditoria import _requisicao_atual, registrar_evento
from .models import EventoAuditoria


class AuditoriaAcessoMiddleware:
    """Registra rota, método e resultado, sem query string, IP ou dados enviados."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _requisicao_atual.set(request)
        try:
            response = self.get_response(request)
            caminho = request.path_info
            if not caminho.startswith(("/static/", "/favicon.ico")):
                registrar_evento(
                    EventoAuditoria.Tipo.ACESSO,
                    usuario=getattr(request, "user", None),
                    # O padrão nomeado evita registrar tokens presentes em URLs de redefinição.
                    rota=getattr(getattr(request, "resolver_match", None), "route", None) or "[rota não resolvida]",
                    metodo=request.method,
                    status_http=response.status_code,
                )
            return response
        finally:
            _requisicao_atual.reset(token)


class RequerAceiteDocumentosMiddleware:
    """Pede novo aceite após atualização das versões da política ou dos termos."""

    ROTAS_LIVRES = (
        "/",
        "/cadastrar/",
        "/politica-de-privacidade/",
        "/termos-de-uso/",
        "/aceitar-documentos/",
        "/sair/",
        "/static/",
        "/favicon.ico",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        caminho = request.path_info
        rota_livre = (
            caminho in self.ROTAS_LIVRES
            or caminho.startswith(("/senha/", "/static/"))
        )
        if (
            getattr(usuario, "is_authenticated", False)
            and not rota_livre
            and (
                usuario.versao_politica != settings.LGPD_POLITICA_VERSAO
                or usuario.versao_termos != settings.LGPD_TERMOS_VERSAO
            )
        ):
            return redirect("aceitar_documentos")
        return self.get_response(request)
