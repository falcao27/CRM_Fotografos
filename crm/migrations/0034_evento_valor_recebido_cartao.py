from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0033_evento_album_campos"),
    ]

    operations = [
        migrations.AddField(
            model_name="evento",
            name="valor_recebido_cartao",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
