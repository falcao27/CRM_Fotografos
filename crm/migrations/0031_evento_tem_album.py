from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0030_reparar_valor_contratado_parcelas"),
    ]

    operations = [
        migrations.AddField(
            model_name="evento",
            name="tem_album",
            field=models.BooleanField(default=False),
        ),
    ]
