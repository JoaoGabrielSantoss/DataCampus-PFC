from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email


class Command(BaseCommand):
    help = "Confere acesso à API do Brevo e se o remetente configurado está ativo (não envia e-mail)."

    def handle(self, *args, **options):
        _, remetente = parseaddr(settings.DEFAULT_FROM_EMAIL)
        if not remetente:
            raise CommandError("EMAIL_REMETENTE não contém um endereço de e-mail válido.")
        try:
            validate_email(remetente)
        except ValidationError as erro:
            raise CommandError("EMAIL_REMETENTE não contém um endereço de e-mail válido.") from erro

        self.stdout.write("Formato do remetente: válido.")
        if not settings.BREVO_API_KEY.strip():
            raise CommandError("BREVO_API_KEY está vazia.")

        try:
            resposta = requests.get(
                "https://api.brevo.com/v3/senders",
                headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
                timeout=10,
            )
        except requests.RequestException as erro:
            raise CommandError(f"Não foi possível consultar o Brevo ({erro.__class__.__name__}).") from erro

        if resposta.status_code in (401, 403):
            try:
                detalhe = resposta.json().get("message", "")
            except ValueError:
                detalhe = ""
            if isinstance(detalhe, str) and 'not authorized for resource "account"' in detalhe.casefold():
                raise CommandError(
                    "A chave foi reconhecida, mas não tem permissão Account: Read, necessária para consultar "
                    "os remetentes. No painel do Brevo, habilite também Transactional email: All para permitir "
                    "que o DataCampus envie mensagens."
                )
            detalhe_seguro = detalhe if isinstance(detalhe, str) and len(detalhe) < 180 else ""
            complemento = f" Motivo informado pelo Brevo: {detalhe_seguro}" if detalhe_seguro else ""
            raise CommandError(
                "O Brevo recusou a autenticação. Confira se BREVO_API_KEY está atualizada e se o IP está autorizado."
                + complemento
            )
        if resposta.status_code >= 400:
            raise CommandError(f"O Brevo respondeu com status HTTP {resposta.status_code}.")

        try:
            remetentes = resposta.json().get("senders", [])
        except (ValueError, AttributeError) as erro:
            raise CommandError("A resposta do Brevo não veio no formato esperado.") from erro

        ativo = any(
            item.get("email", "").casefold() == remetente.casefold() and item.get("active") is True
            for item in remetentes
        )
        if not ativo:
            raise CommandError(
                "A API aceitou a chave, mas o remetente configurado não aparece como ativo/verificado no Brevo."
            )
        self.stdout.write(self.style.SUCCESS("Brevo autenticado; remetente configurado ativo/verificado."))
        self.stdout.write("Nenhum e-mail foi enviado por esta verificação.")
