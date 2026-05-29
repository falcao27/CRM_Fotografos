from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Evento, Tarefa


def titulo_trabalho_evento(evento):
    return evento.get_tipo_evento_display() if evento.tipo_evento else evento.nome


def descricao_trabalho_evento(evento):
    linhas = []
    if evento.local_evento:
        linhas.append(f"Local: {evento.local_evento}")
    linhas.append(f"Buffet: {'Sim' if evento.em_buffet else 'Nao'}")
    if evento.observacoes:
        linhas.append(evento.observacoes)
    return "\n".join(linhas)


@receiver(post_save, sender=Evento)
def sincronizar_evento_com_agenda(sender, instance, **kwargs):
    if not instance.data_festa:
        Tarefa.objects.filter(evento=instance).delete()
        return

    Tarefa.objects.update_or_create(
        evento=instance,
        defaults={
            "cliente": instance.cliente,
            "titulo": titulo_trabalho_evento(instance),
            "tipo": "trabalho",
            "data": instance.data_festa,
            "hora": instance.horario,
            "status": "pendente",
            "descricao": descricao_trabalho_evento(instance),
        },
    )
