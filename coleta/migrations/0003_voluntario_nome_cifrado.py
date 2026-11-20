from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("coleta", "0002_remove_dadocoletado_dado_unico_por_voluntario_variavel_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="voluntario",
            name="nome_cifrado",
            field=models.TextField(blank=True, default="", verbose_name="nome cifrado"),
        ),
    ]
