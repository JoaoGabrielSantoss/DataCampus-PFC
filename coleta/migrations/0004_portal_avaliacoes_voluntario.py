import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("coleta", "0003_voluntario_nome_cifrado"),
    ]

    operations = [
        migrations.AddField(
            model_name="voluntario",
            name="email_cifrado",
            field=models.TextField(blank=True, default="", verbose_name="e-mail cifrado"),
        ),
        migrations.CreateModel(
            name="CodigoAcessoVoluntario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo_hash", models.CharField(max_length=128, verbose_name="hash do código")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="criado em")),
                ("expira_em", models.DateTimeField(verbose_name="expira em")),
                ("tentativas", models.PositiveSmallIntegerField(default=0, verbose_name="tentativas")),
                ("usado_em", models.DateTimeField(blank=True, null=True, verbose_name="usado em")),
                ("voluntario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="codigos_acesso", to="coleta.voluntario")),
            ],
            options={
                "verbose_name": "código de acesso do voluntário",
                "verbose_name_plural": "códigos de acesso dos voluntários",
                "ordering": ["-criado_em"],
            },
        ),
        migrations.CreateModel(
            name="AvaliacaoParticipacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nota_estudo", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(5)], verbose_name="avaliação da pesquisa")),
                ("nota_pesquisador", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(5)], verbose_name="avaliação do pesquisador")),
                ("comentario", models.CharField(blank=True, max_length=1000, verbose_name="comentário para o pesquisador")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("participacao", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="avaliacao", to="coleta.participacao")),
            ],
            options={
                "verbose_name": "avaliação da participação",
                "verbose_name_plural": "avaliações das participações",
                "ordering": ["-atualizado_em"],
            },
        ),
    ]
