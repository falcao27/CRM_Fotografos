from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0031_evento_tem_album"),
    ]

    operations = [
        migrations.AddField(
            model_name="evento",
            name="edicao_backup",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_cliente_pais",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_contato",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_data",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_data_entrega",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_editado",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_selecao",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_status",
            field=models.CharField(
                choices=[("pendente", "Pendente"), ("finalizado", "Finalizado")],
                default="pendente",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_tipo_servico",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="evento",
            name="edicao_aniversariantes",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
