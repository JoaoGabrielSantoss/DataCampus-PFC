from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UsuarioManager(BaseUserManager):
    def create_user(self, email, nome_completo, password=None, **extra_fields):
        if not email:
            raise ValueError("O email é obrigatório.")
        usuario = self.model(
            email=self.normalize_email(email),
            nome_completo=nome_completo,
            **extra_fields,
        )
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, nome_completo, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields["is_staff"] is not True:
            raise ValueError("Um superusuário precisa ter is_staff=True.")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("Um superusuário precisa ter is_superuser=True.")
        return self.create_user(email, nome_completo, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    class Perfil(models.TextChoices):
        PESQUISADOR = "pesquisador", "pesquisador"
        PROFISSIONAL = "profissional", "profissional"

    nome_completo = models.CharField("nome completo", max_length=150)
    email = models.EmailField("email", unique=True)
    # O padrão é o perfil de menor alcance.
    perfil = models.CharField("perfil", max_length=12, choices=Perfil.choices, default=Perfil.PROFISSIONAL)
    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("equipe", default=False)
    aceitou_politica_em = models.DateTimeField("leu a política em", null=True, blank=True)
    versao_politica = models.CharField("versão da política", max_length=20, blank=True)
    aceitou_termos_em = models.DateTimeField("aceitou os termos em", null=True, blank=True)
    versao_termos = models.CharField("versão dos termos", max_length=20, blank=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome_completo", "perfil"]

    def __str__(self):
        return self.email

    @property
    def iniciais(self):
        partes = self.nome_completo.split()
        if not partes:
            return self.email[:2].upper()
        return (partes[0][0] + partes[-1][0]).upper() if len(partes) > 1 else partes[0][:2].upper()

    @property
    def e_pesquisador(self):
        return self.perfil == self.Perfil.PESQUISADOR

    @property
    def e_profissional(self):
        return self.perfil == self.Perfil.PROFISSIONAL


class EventoAuditoria(models.Model):
    class Tipo(models.TextChoices):
        ACESSO = "acesso", "Acesso"
        LOGIN = "login", "Login"
        LOGIN_FALHOU = "login_falhou", "Tentativa de login"
        LOGOUT = "logout", "Logout"
        CRIACAO = "criacao", "Criação"
        ALTERACAO = "alteracao", "Alteração"
        EXCLUSAO = "exclusao", "Exclusão"

    usuario = models.ForeignKey(
        "autenticacao.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
        verbose_name="usuário",
    )
    tipo = models.CharField("tipo", max_length=20, choices=Tipo.choices, db_index=True)
    rota = models.CharField("rota", max_length=255, blank=True)
    metodo = models.CharField("método HTTP", max_length=10, blank=True)
    status_http = models.PositiveSmallIntegerField("status HTTP", null=True, blank=True)
    modelo_alvo = models.CharField("modelo afetado", max_length=100, blank=True)
    id_alvo = models.CharField("identificador do registro", max_length=80, blank=True)
    campos_alterados = models.JSONField("nomes dos campos alterados", default=list, blank=True)
    criado_em = models.DateTimeField("data e hora", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "evento de auditoria"
        verbose_name_plural = "eventos de auditoria"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["usuario", "-criado_em"], name="auditoria_user_data_idx"),
            models.Index(fields=["tipo", "-criado_em"], name="auditoria_tipo_data_idx"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.criado_em:%d/%m/%Y %H:%M}"
