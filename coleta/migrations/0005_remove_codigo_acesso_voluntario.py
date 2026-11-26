from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("coleta", "0004_portal_avaliacoes_voluntario"),
    ]

    operations = [
        migrations.DeleteModel(name="CodigoAcessoVoluntario"),
    ]
