from django.db import migrations, models
import django.db.models.deletion


def criar_trabalhos_dos_eventos(apps, schema_editor):
    Evento = apps.get_model("crm", "Evento")
    Tarefa = apps.get_model("crm", "Tarefa")
    choices = dict(Evento._meta.get_field("tipo_evento").choices)

    for evento in Evento.objects.exclude(data_festa__isnull=True):
        Tarefa.objects.update_or_create(
            evento=evento,
            defaults={
                "cliente": evento.cliente,
                "titulo": choices.get(evento.tipo_evento, evento.tipo_evento or evento.nome),
                "tipo": "trabalho",
                "data": evento.data_festa,
                "hora": evento.horario,
                "status": "pendente",
                "descricao": evento.observacoes,
            },
        )


def remover_trabalhos_automaticos(apps, schema_editor):
    Tarefa = apps.get_model("crm", "Tarefa")
    Tarefa.objects.exclude(evento__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0012_oportunidade_valor_negociado"),
    ]

    operations = [
        migrations.AddField(
            model_name="tarefa",
            name="evento",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="agenda_trabalho",
                to="crm.evento",
            ),
        ),
        migrations.RunPython(criar_trabalhos_dos_eventos, remover_trabalhos_automaticos),
    ]
