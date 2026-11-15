from django.conf import settings
from django.db import models

from .seguranca import cifrar, decifrar


class Voluntario(models.Model):
    identificador = models.CharField("identificador pseudonimizado", max_length=64, unique=True)
    cpf_cifrado = models.TextField("CPF cifrado")
    autorizou_reuso_em = models.DateTimeField("autorização de reuso registrada em", null=True, blank=True)
    criado_em = models.DateTimeField("cadastrado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voluntarios_cadastrados",
        verbose_name="cadastrado por",
    )

    class Meta:
        verbose_name = "voluntário"
        verbose_name_plural = "voluntários"
        ordering = ["criado_em"]

    def __str__(self):
        return self.codigo_publico

    @property
    def codigo_publico(self):
        return f"VOL-{self.identificador[:8].upper()}"

    def obter_cpf(self):
        return decifrar(self.cpf_cifrado)

    @classmethod
    def registrar(cls, cpf, *, autorizado_reuso, usuario):
        from django.utils import timezone

        from .seguranca import identificador_cpf, validar_cpf

        cpf_limpo = validar_cpf(cpf)
        identificador = identificador_cpf(cpf_limpo)
        voluntario, criado = cls.objects.get_or_create(
            identificador=identificador,
            defaults={
                "cpf_cifrado": cifrar(cpf_limpo),
                "autorizou_reuso_em": timezone.now() if autorizado_reuso else None,
                "criado_por": usuario,
            },
        )
        autorizacao_atualizada = False
        if not criado and autorizado_reuso and voluntario.autorizou_reuso_em is None:
            voluntario.autorizou_reuso_em = timezone.now()
            voluntario.save(update_fields=["autorizou_reuso_em"])
            autorizacao_atualizada = True
        return voluntario, criado, autorizacao_atualizada


class DadoColetado(models.Model):
    voluntario = models.ForeignKey(Voluntario, on_delete=models.CASCADE, related_name="dados")
    variavel = models.ForeignKey("catalogo.Variavel", on_delete=models.PROTECT, related_name="dados_coletados")
    valor_cifrado = models.TextField("valor cifrado")
    coletado_em = models.DateTimeField("coletado em", auto_now=True)
    coletado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dados_coletados",
        verbose_name="coletado por",
    )
    estudo_origem = models.ForeignKey(
        "estudos.Estudo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dados_coletados",
        verbose_name="estudo de origem",
    )

    class Meta:
        verbose_name = "dado coletado"
        verbose_name_plural = "dados coletados"
        ordering = ["variavel__codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["voluntario", "variavel", "estudo_origem"],
                name="dado_unico_por_voluntario_variavel_estudo",
            ),
        ]

    def __str__(self):
        return f"{self.voluntario.codigo_publico} — {self.variavel.nome}"

    def definir_valor(self, valor):
        import json

        self.valor_cifrado = cifrar(json.dumps(valor, ensure_ascii=False, separators=(",", ":")))

    def obter_valor(self):
        import json

        return json.loads(decifrar(self.valor_cifrado))


class Participacao(models.Model):
    class Situacao(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        ELEGIVEL = "elegivel", "Elegível"
        INELEGIVEL = "inelegivel", "Inelegível"

    estudo = models.ForeignKey("estudos.Estudo", on_delete=models.CASCADE, related_name="participacoes")
    voluntario = models.ForeignKey(Voluntario, on_delete=models.CASCADE, related_name="participacoes")
    profissional = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="participacoes_atendidas",
        verbose_name="profissional responsável",
    )
    dados_utilizados = models.ManyToManyField(DadoColetado, blank=True, related_name="participacoes")
    situacao = models.CharField(
        "situação da elegibilidade", max_length=12, choices=Situacao.choices, default=Situacao.PENDENTE, db_index=True
    )
    criado_em = models.DateTimeField("vinculado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "participação em estudo"
        verbose_name_plural = "participações em estudos"
        ordering = ["-atualizado_em"]
        constraints = [
            models.UniqueConstraint(fields=["estudo", "voluntario"], name="participacao_unica_por_estudo_voluntario"),
        ]

    def __str__(self):
        return f"{self.voluntario.codigo_publico} — {self.estudo.nome}"
