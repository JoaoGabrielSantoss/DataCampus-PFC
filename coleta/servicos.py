import calendar
from datetime import date
from decimal import Decimal

from catalogo.models import Operador, Variavel

from .models import DadoColetado, Participacao


def valores_conhecidos(participacao):
    return {
        dado.variavel_id: dado.obter_valor()
        for dado in participacao.dados_utilizados.select_related("variavel")
    }


def dados_reutilizaveis(voluntario, ids_variaveis):
    """Retorna dados do voluntário somente quando há autorização registrada."""
    if not voluntario.autorizou_reuso_em:
        return DadoColetado.objects.none()
    return voluntario.dados.filter(variavel_id__in=ids_variaveis)


def _comparar(criterio, valor):
    variavel = criterio.variavel
    operador = criterio.operador

    if variavel.tipo == Variavel.Tipo.NUMERICA:
        valor = Decimal(str(valor))
        a = criterio.valor_numero
        b = criterio.valor_numero_ate
        return {
            Operador.IGUAL: lambda: valor == a,
            Operador.DIFERENTE: lambda: valor != a,
            Operador.MENOR: lambda: valor < a,
            Operador.MENOR_IGUAL: lambda: valor <= a,
            Operador.MAIOR: lambda: valor > a,
            Operador.MAIOR_IGUAL: lambda: valor >= a,
            Operador.ENTRE: lambda: a <= valor <= b,
        }[Operador(operador)]()

    if variavel.tipo == Variavel.Tipo.DATA:
        valor = date.fromisoformat(str(valor))
        a = criterio.valor_data
        b = criterio.valor_data_ate
        return {
            Operador.ANTES: lambda: valor < a,
            Operador.DEPOIS: lambda: valor > a,
            Operador.ENTRE: lambda: a <= valor <= b,
        }[Operador(operador)]()

    if variavel.tipo in (Variavel.Tipo.NOMINAL, Variavel.Tipo.ORDINAL):
        opcao = variavel.dominio.opcoes.filter(pk=int(valor)).first()
        if opcao is None:
            return False
        opcoes = list(criterio.opcoes.all())
        ids = {item.pk for item in opcoes}
        if variavel.tipo == Variavel.Tipo.NOMINAL:
            return {
                Operador.E: lambda: opcao.pk == opcoes[0].pk,
                Operador.NAO_E: lambda: opcao.pk != opcoes[0].pk,
                Operador.ESTA_EM: lambda: opcao.pk in ids,
                Operador.NAO_ESTA_EM: lambda: opcao.pk not in ids,
            }[Operador(operador)]()

        ordens = [item.ordem for item in opcoes]
        return {
            Operador.E: lambda: opcao.pk == opcoes[0].pk,
            Operador.NAO_E: lambda: opcao.pk != opcoes[0].pk,
            Operador.ESTA_EM: lambda: opcao.pk in ids,
            Operador.NAO_ESTA_EM: lambda: opcao.pk not in ids,
            Operador.MENOR_IGUAL: lambda: opcao.ordem <= ordens[0],
            Operador.MAIOR_IGUAL: lambda: opcao.ordem >= ordens[0],
            Operador.ENTRE: lambda: min(ordens) <= opcao.ordem <= max(ordens),
        }[Operador(operador)]()

    if variavel.tipo == Variavel.Tipo.BOOLEANA:
        valor = bool(valor)
        return valor if operador == Operador.VERDADEIRO else not valor

    return False


def avaliar_estudo(estudo, valores):
    pendentes = []
    reprovado = False
    criterios = estudo.criterios.select_related("variavel", "variavel__dominio").prefetch_related("opcoes")
    for criterio in criterios:
        valor = valores.get(criterio.variavel_id)
        if valor is None:
            pendentes.append(criterio.variavel)
        elif not _comparar(criterio, valor):
            reprovado = True

    if reprovado:
        return Participacao.Situacao.INELEGIVEL, pendentes
    if pendentes:
        return Participacao.Situacao.PENDENTE, pendentes
    return Participacao.Situacao.ELEGIVEL, []


def variaveis_pendentes(participacao):
    valores = valores_conhecidos(participacao)
    return [
        criterio.variavel
        for criterio in participacao.estudo.criterios.select_related("variavel")
        if criterio.variavel_id not in valores
    ]


def preparar_valor(campo, valor):
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    if hasattr(valor, "pk"):
        return valor.pk
    if isinstance(valor, str) and valor in {"true", "false"}:
        return valor == "true"
    return valor
