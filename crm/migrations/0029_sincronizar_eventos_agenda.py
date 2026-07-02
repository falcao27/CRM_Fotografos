from django.db import migrations


def titulo_trabalho_evento(evento):
    escolhas = dict(evento._meta.get_field("tipo_evento").choices)
    return escolhas.get(evento.tipo_evento) or evento.tipo_evento or evento.nome


def descricao_trabalho_evento(evento):
    linhas = []
    if evento.local_evento:
        linhas.append(f"Local: {evento.local_evento}")
    linhas.append(f"Buffet: {'Sim' if evento.em_buffet else 'Nao'}")
    if evento.observacoes:
        linhas.append(evento.observacoes)
    return "\n".join(linhas)


def sincronizar_eventos(apps, schema_editor):
    Evento = apps.get_model("crm", "Evento")
    Tarefa = apps.get_model("crm", "Tarefa")

    for evento in Evento.objects.all().iterator():
        if not evento.data_festa:
            Tarefa.objects.filter(evento=evento).delete()
            continue

        Tarefa.objects.update_or_create(
            evento=evento,
            defaults={
                "empresa": evento.empresa,
                "cliente": evento.cliente,
                "nome_contato": "" if evento.cliente_id else evento.nome,
                "titulo": titulo_trabalho_evento(evento),
                "tipo": "trabalho",
                "data": evento.data_festa,
                "hora": evento.horario,
                "status": "pendente",
                "descricao": descricao_trabalho_evento(evento),
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0028_tarefa_nome_contato"),
    ]

    operations = [
        migrations.RunPython(sincronizar_eventos, migrations.RunPython.noop),
    ]
