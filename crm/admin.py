from django.contrib import admin

from .models import Cliente, Despesa, Documento, Evento, LembreteAnual, Oportunidade, OportunidadePerdida, Parcela, Tarefa, Venda


class ParcelaInline(admin.TabularInline):
    model = Parcela
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "telefone", "email", "tipo_evento", "proxima_oportunidade")
    search_fields = ("nome", "telefone", "email")


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "cliente", "valor_total", "status", "forma_pagamento", "data_venda")
    list_filter = ("status", "forma_pagamento", "condicao_pagamento")
    search_fields = ("titulo", "cliente__nome")
    inlines = [ParcelaInline]


@admin.register(Parcela)
class ParcelaAdmin(admin.ModelAdmin):
    list_display = ("venda", "numero", "valor", "vencimento", "status", "lembrete_em")
    list_filter = ("status", "vencimento")


@admin.register(Despesa)
class DespesaAdmin(admin.ModelAdmin):
    list_display = ("descricao", "categoria", "valor", "data", "status", "forma_pagamento")
    list_filter = ("status", "forma_pagamento", "categoria")


@admin.register(Oportunidade)
class OportunidadeAdmin(admin.ModelAdmin):
    list_display = ("nome_lead", "titulo", "tipo_evento", "etapa", "data_festa", "contato")
    list_filter = ("etapa", "prioridade")
    search_fields = ("nome_lead", "titulo")


@admin.register(OportunidadePerdida)
class OportunidadePerdidaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo_prospeccao", "tipo_evento", "data_festa", "contato", "atualizado_em")
    search_fields = ("nome", "contato", "tipo_evento")


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "cliente",
        "tipo_evento",
        "data_festa",
        "valor_cobrado",
        "forma_pagamento",
        "pagamento_recebido",
        "quantidade_parcelas",
        "contato",
    )
    search_fields = ("nome", "cliente__nome", "contato")


@admin.register(LembreteAnual)
class LembreteAnualAdmin(admin.ModelAdmin):
    list_display = ("nome", "data_original", "data_proximo_evento", "data_alerta", "contato")
    search_fields = ("nome", "contato")


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "cliente", "tipo", "data", "hora", "status")
    list_filter = ("tipo", "status", "data")


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "cliente", "status", "forma_envio", "contato_whatsapp", "contato_email", "data_limite")
    list_filter = ("status", "forma_envio")
