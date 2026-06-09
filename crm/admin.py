from django.contrib import admin

from .models import (
    AcessoUsuario,
    AdminCompromisso,
    Cliente,
    ContratoAdminEmpresa,
    Despesa,
    Documento,
    Empresa,
    Evento,
    LembreteAnual,
    Oportunidade,
    OportunidadePerdida,
    Parcela,
    PerfilUsuario,
    Tarefa,
    Venda,
)


def usuario_admin_master(user):
    perfil = getattr(user, "perfil_crm", None)
    return bool(user.is_superuser or (perfil and perfil.admin_master))


def empresa_usuario(user):
    perfil = getattr(user, "perfil_crm", None)
    if not perfil or perfil.admin_master:
        return None
    return perfil.empresa


def objeto_pertence_empresa(obj, empresa):
    if not obj or not empresa:
        return True
    if hasattr(obj, "empresa_id"):
        return obj.empresa_id == empresa.id
    if hasattr(obj, "venda") and obj.venda_id:
        return obj.venda.empresa_id == empresa.id
    if hasattr(obj, "cliente") and obj.cliente_id:
        return obj.cliente.empresa_id == empresa.id
    if hasattr(obj, "evento") and obj.evento_id:
        return obj.evento.empresa_id == empresa.id
    return False


class AdminMasterOnlyMixin:
    def has_module_permission(self, request):
        return usuario_admin_master(request.user)

    def has_view_permission(self, request, obj=None):
        return usuario_admin_master(request.user)

    def has_add_permission(self, request):
        return usuario_admin_master(request.user)

    def has_change_permission(self, request, obj=None):
        return usuario_admin_master(request.user)

    def has_delete_permission(self, request, obj=None):
        return usuario_admin_master(request.user)


class ClienteOnlyMixin:
    def has_module_permission(self, request):
        return bool(request.user.is_staff and empresa_usuario(request.user))

    def has_view_permission(self, request, obj=None):
        empresa = empresa_usuario(request.user)
        return bool(request.user.is_staff and empresa and objeto_pertence_empresa(obj, empresa))

    def has_add_permission(self, request):
        return bool(request.user.is_staff and empresa_usuario(request.user))

    def has_change_permission(self, request, obj=None):
        empresa = empresa_usuario(request.user)
        return bool(request.user.is_staff and empresa and objeto_pertence_empresa(obj, empresa))

    def has_delete_permission(self, request, obj=None):
        empresa = empresa_usuario(request.user)
        return bool(request.user.is_staff and empresa and objeto_pertence_empresa(obj, empresa))

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        empresa = empresa_usuario(request.user)
        if not empresa:
            return qs.none()
        if hasattr(self.model, "empresa"):
            return qs.filter(empresa=empresa)
        if self.model is Parcela:
            return qs.filter(venda__empresa=empresa)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        empresa = empresa_usuario(request.user)
        if empresa:
            if db_field.name == "cliente":
                kwargs["queryset"] = Cliente.objects.filter(empresa=empresa)
            elif db_field.name == "evento":
                kwargs["queryset"] = Evento.objects.filter(empresa=empresa)
            elif db_field.name == "venda":
                kwargs["queryset"] = Venda.objects.filter(empresa=empresa)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        empresa = empresa_usuario(request.user)
        if empresa and hasattr(obj, "empresa_id"):
            obj.empresa = empresa
        super().save_model(request, obj, form, change)


@admin.register(Empresa)
class EmpresaAdmin(AdminMasterOnlyMixin, admin.ModelAdmin):
    list_display = ("nome", "email", "telefone", "ativa", "criado_em")
    list_filter = ("ativa",)
    search_fields = ("nome", "email", "telefone")


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(AdminMasterOnlyMixin, admin.ModelAdmin):
    list_display = ("user", "empresa", "papel", "ultimo_acesso", "online_ate")
    list_filter = ("papel", "empresa")
    search_fields = ("user__username", "user__email", "empresa__nome")


@admin.register(AcessoUsuario)
class AcessoUsuarioAdmin(AdminMasterOnlyMixin, admin.ModelAdmin):
    list_display = ("user", "empresa", "caminho", "ip", "criado_em")
    list_filter = ("empresa", "criado_em")
    search_fields = ("user__username", "empresa__nome", "caminho", "ip")


@admin.register(ContratoAdminEmpresa)
class ContratoAdminEmpresaAdmin(AdminMasterOnlyMixin, admin.ModelAdmin):
    list_display = ("empresa", "descricao", "valor", "vencimento", "status", "data_pagamento")
    list_filter = ("status", "vencimento", "empresa")
    search_fields = ("empresa__nome", "descricao")


@admin.register(AdminCompromisso)
class AdminCompromissoAdmin(AdminMasterOnlyMixin, admin.ModelAdmin):
    list_display = ("titulo", "empresa", "tipo", "data", "hora", "status")
    list_filter = ("tipo", "status", "data", "empresa")
    search_fields = ("titulo", "empresa__nome", "descricao")


class ParcelaInline(admin.TabularInline):
    model = Parcela
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("nome", "telefone", "email", "tipo_evento", "proxima_oportunidade")
    search_fields = ("nome", "telefone", "email")


@admin.register(Venda)
class VendaAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("titulo", "cliente", "valor_total", "status", "forma_pagamento", "data_venda")
    list_filter = ("status", "forma_pagamento", "condicao_pagamento")
    search_fields = ("titulo", "cliente__nome")
    inlines = [ParcelaInline]


@admin.register(Parcela)
class ParcelaAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("venda", "numero", "valor", "valor_recebido", "vencimento", "status", "lembrete_em")
    list_filter = ("status", "vencimento")


@admin.register(Despesa)
class DespesaAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("descricao", "categoria", "valor", "data", "status", "forma_pagamento")
    list_filter = ("status", "forma_pagamento", "categoria")


@admin.register(Oportunidade)
class OportunidadeAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("nome_lead", "titulo", "tipo_evento", "etapa", "data_festa", "contato")
    list_filter = ("etapa", "prioridade")
    search_fields = ("nome_lead", "titulo")


@admin.register(OportunidadePerdida)
class OportunidadePerdidaAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("nome", "tipo_prospeccao", "tipo_evento", "data_festa", "contato", "atualizado_em")
    search_fields = ("nome", "contato", "tipo_evento")


@admin.register(Evento)
class EventoAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = (
        "nome",
        "cliente",
        "tipo_evento",
        "data_festa",
        "local_evento",
        "em_buffet",
        "valor_cobrado",
        "forma_pagamento",
        "pagamento_recebido",
        "quantidade_parcelas",
        "contato",
    )
    search_fields = ("nome", "cliente__nome", "contato")


@admin.register(LembreteAnual)
class LembreteAnualAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("nome", "data_original", "data_proximo_evento", "data_alerta", "contato")
    search_fields = ("nome", "contato")


@admin.register(Tarefa)
class TarefaAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("titulo", "cliente", "tipo", "data", "hora", "status")
    list_filter = ("tipo", "status", "data")


@admin.register(Documento)
class DocumentoAdmin(ClienteOnlyMixin, admin.ModelAdmin):
    list_display = ("titulo", "cliente", "status", "forma_envio", "contato_whatsapp", "contato_email", "data_limite")
    list_filter = ("status", "forma_envio")
