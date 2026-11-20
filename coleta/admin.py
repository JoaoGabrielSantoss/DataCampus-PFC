from django.contrib import admin

from .models import DadoColetado, Participacao, Voluntario


@admin.register(Voluntario)
class VoluntarioAdmin(admin.ModelAdmin):
    list_display = ("nome_publico", "criado_em", "autorizou_reuso_em")
    search_fields = ("identificador",)
    readonly_fields = ("identificador", "nome_cifrado", "cpf_cifrado", "criado_em", "criado_por")


@admin.register(DadoColetado)
class DadoColetadoAdmin(admin.ModelAdmin):
    list_display = ("voluntario", "variavel", "coletado_em", "estudo_origem")
    readonly_fields = ("valor_cifrado", "coletado_em")


@admin.register(Participacao)
class ParticipacaoAdmin(admin.ModelAdmin):
    list_display = ("estudo", "voluntario", "situacao", "atualizado_em")
    list_filter = ("situacao", "estudo__situacao")
    readonly_fields = ("criado_em", "atualizado_em")
