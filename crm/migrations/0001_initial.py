# Generated manually for the CRM Fotografos app.

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Cliente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=160)),
                ("telefone", models.CharField(blank=True, max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("origem", models.CharField(blank=True, max_length=80)),
                ("tipo_evento", models.CharField(blank=True, max_length=100)),
                ("data_evento", models.DateField(blank=True, null=True)),
                (
                    "proxima_oportunidade",
                    models.DateField(blank=True, help_text="Data prevista para tentar uma nova venda.", null=True),
                ),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["nome"]},
        ),
        migrations.CreateModel(
            name="Venda",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=160)),
                ("data_venda", models.DateField(default=django.utils.timezone.localdate)),
                ("valor_total", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pendente", "Pendente"),
                            ("pago", "Pago"),
                            ("atrasado", "Atrasado"),
                            ("cancelado", "Cancelado"),
                        ],
                        default="pendente",
                        max_length=20,
                    ),
                ),
                (
                    "forma_pagamento",
                    models.CharField(
                        choices=[
                            ("pix", "Pix"),
                            ("dinheiro", "Dinheiro"),
                            ("boleto", "Boleto"),
                            ("cartao", "Cartao"),
                            ("transferencia", "Transferencia"),
                            ("outro", "Outro"),
                        ],
                        default="pix",
                        max_length=20,
                    ),
                ),
                (
                    "condicao_pagamento",
                    models.CharField(choices=[("avista", "A vista"), ("parcelado", "Parcelado")], default="avista", max_length=20),
                ),
                ("quantidade_parcelas", models.PositiveIntegerField(default=1)),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "cliente",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vendas", to="crm.cliente"),
                ),
            ],
            options={"ordering": ["-data_venda", "-id"]},
        ),
        migrations.CreateModel(
            name="Parcela",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.PositiveIntegerField()),
                ("valor", models.DecimalField(decimal_places=2, max_digits=10)),
                ("vencimento", models.DateField()),
                ("data_pagamento", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("pendente", "Pendente"), ("pago", "Pago"), ("atrasado", "Atrasado")],
                        default="pendente",
                        max_length=20,
                    ),
                ),
                ("lembrete_em", models.DateField(blank=True, null=True)),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "venda",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parcelas", to="crm.venda"),
                ),
            ],
            options={"ordering": ["vencimento", "numero"], "unique_together": {("venda", "numero")}},
        ),
    ]

