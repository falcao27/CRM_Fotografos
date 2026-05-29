from django.db import migrations, models


def atualizar_trabalhos_da_agenda(apps, schema_editor):
    Tarefa = apps.get_model("crm", "Tarefa")
    for tarefa in Tarefa.objects.exclude(evento__isnull=True).select_related("evento"):
        evento = tarefa.evento
        linhas = []
        if evento.local_evento:
            linhas.append(f"Local: {evento.local_evento}")
        linhas.append(f"Buffet: {'Sim' if evento.em_buffet else 'Nao'}")
        if evento.observacoes:
            linhas.append(evento.observacoes)
        tarefa.descricao = "\n".join(linhas)
        tarefa.save(update_fields=["descricao"])


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0013_tarefa_evento_agenda_trabalhos"),
    ]

    operations = [
        migrations.AddField(
            model_name="evento",
            name="local_evento",
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name="evento",
            name="em_buffet",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(atualizar_trabalhos_da_agenda, migrations.RunPython.noop),
    ]
