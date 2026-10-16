from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import EventoAuditoria, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    model = Usuario
    ordering = ("email",)
    list_display = ("email", "nome_completo", "perfil", "is_active", "is_staff")
    list_filter = ("perfil", "is_active", "is_staff")
    search_fields = ("email", "nome_completo")
    readonly_fields = ("aceitou_politica_em", "versao_politica", "aceitou_termos_em", "versao_termos")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("nome_completo",)}),
        ("Perfil", {"fields": ("perfil",)}),
        ("Avisos legais", {"fields": readonly_fields}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "nome_completo", "perfil", "password1", "password2", "is_active", "is_staff")}),
    )


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "tipo", "usuario", "metodo", "rota", "status_http", "modelo_alvo", "id_alvo")
    list_filter = ("tipo", "metodo", "status_http", "criado_em")
    search_fields = ("usuario__email", "rota", "modelo_alvo", "id_alvo")
    readonly_fields = (
        "usuario", "tipo", "rota", "metodo", "status_http", "modelo_alvo",
        "id_alvo", "campos_alterados", "criado_em",
    )
    ordering = ("-criado_em",)
    date_hierarchy = "criado_em"

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        # Permite consultar os registros sem liberar edição.
        return request.user.is_active and request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
