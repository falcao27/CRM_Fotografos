from decimal import Decimal

from django.db import migrations


def reparar_valores_contratados(apps, schema_editor):
    Venda = apps.get_model("crm", "Venda")

    for venda in Venda.objects.prefetch_related("parcelas"):
        parcelas = list(venda.parcelas.order_by("numero", "vencimento", "id"))
        if not parcelas:
            continue

        total_parcelas = sum((parcela.valor for parcela in parcelas), Decimal("0.00"))
        diferenca = total_parcelas - venda.valor_total
        if diferenca == Decimal("0.00"):
            continue

        candidatas = [
            parcela
            for parcela in parcelas
            if parcela.status == "pago" and parcela.valor_recebido and parcela.valor_recebido == parcela.valor
        ]
        if not candidatas:
            candidatas = [parcela for parcela in parcelas if parcela.status == "pago" and parcela.valor_recebido]
        if not candidatas:
            continue

        restante = diferenca
        for parcela in reversed(candidatas):
            if restante == Decimal("0.00"):
                break
            novo_valor = parcela.valor - restante
            if novo_valor <= Decimal("0.00"):
                restante -= parcela.valor
                parcela.valor = Decimal("0.00")
            else:
                parcela.valor = novo_valor
                restante = Decimal("0.00")
            parcela.save(update_fields=["valor"])


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0029_sincronizar_eventos_agenda"),
    ]

    operations = [
        migrations.RunPython(reparar_valores_contratados, migrations.RunPython.noop),
    ]
