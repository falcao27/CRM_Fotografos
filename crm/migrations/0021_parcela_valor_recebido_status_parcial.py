from django.db import migrations, models


def preencher_valor_recebido(apps, schema_editor):
    Parcela = apps.get_model("crm", "Parcela")
    Parcela.objects.filter(status="pago", valor_recebido=0).update(valor_recebido=models.F("valor"))


def limpar_valor_recebido(apps, schema_editor):
    Parcela = apps.get_model("crm", "Parcela")
    Parcela.objects.update(valor_recebido=0)


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0020_alter_documento_conteudo_contrato"),
    ]

    operations = [
        migrations.AlterField(
            model_name="parcela",
            name="status",
            field=models.CharField(
                choices=[
                    ("pendente", "Pendente"),
                    ("parcial", "Parcial"),
                    ("pago", "Pago"),
                    ("atrasado", "Atrasado"),
                ],
                default="pendente",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="parcela",
            name="valor_recebido",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.RunPython(preencher_valor_recebido, limpar_valor_recebido),
    ]
