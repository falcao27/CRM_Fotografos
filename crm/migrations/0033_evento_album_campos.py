from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0032_evento_edicao_campos"),
    ]

    operations = [
        migrations.AddField(
            model_name="evento",
            name="album_data_envio",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="album_data_recebimento",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="album_status",
            field=models.CharField(
                choices=[("pendente", "Pendente"), ("finalizado", "Finalizado")],
                default="pendente",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="evento",
            name="album_tipo",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
