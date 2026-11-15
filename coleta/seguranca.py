import hashlib
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


def normalizar_cpf(valor):
    return re.sub(r"\D", "", valor or "")


def validar_cpf(valor):
    cpf = normalizar_cpf(valor)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        raise ValidationError("Informe um CPF válido.")

    numeros = [int(digito) for digito in cpf]
    for quantidade, peso_inicial in ((9, 10), (10, 11)):
        soma = sum(numero * peso for numero, peso in zip(numeros[:quantidade], range(peso_inicial, 1, -1)))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if numeros[quantidade] != digito:
            raise ValidationError("Informe um CPF válido.")
    return cpf


def identificador_cpf(cpf):
    chave = settings.DATACAMPUS_HMAC_KEY
    if len(chave.encode("utf-8")) < 32:
        raise ImproperlyConfigured("Defina DATACAMPUS_HMAC_KEY com pelo menos 32 bytes no arquivo .env.")
    cpf_normalizado = validar_cpf(cpf)
    return hmac.new(chave.encode("utf-8"), cpf_normalizado.encode("ascii"), hashlib.sha256).hexdigest()


def _cifrador():
    chave = settings.DATACAMPUS_FERNET_KEY
    if not chave:
        raise ImproperlyConfigured("Defina DATACAMPUS_FERNET_KEY no arquivo .env.")
    try:
        return Fernet(chave.encode("ascii"))
    except (ValueError, TypeError) as erro:
        raise ImproperlyConfigured("DATACAMPUS_FERNET_KEY não é uma chave Fernet válida.") from erro


def cifrar(texto):
    return _cifrador().encrypt(str(texto).encode("utf-8")).decode("ascii")


def decifrar(token):
    try:
        return _cifrador().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as erro:
        raise ValidationError("Não foi possível ler o dado cifrado. Confira a chave de dados configurada.") from erro
