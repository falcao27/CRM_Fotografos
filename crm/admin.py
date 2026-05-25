from django.contrib import admin

from .models import Cliente, Despesa, Documento, Oportunidade, Parcela, Tarefa, Venda


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
    list_display = ("nome_lead", "titulo", "valor_estimado", "etapa", "proximo_contato")
    list_filter = ("etapa", "prioridade")
    search_fields = ("nome_lead", "titulo")


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "cliente", "tipo", "data", "hora", "status")
    list_filter = ("tipo", "status", "data")


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "cliente", "status", "forma_envio", "contato_whatsapp", "contato_email", "data_limite")
    list_filter = ("status", "forma_envio")
