from django import forms

from .models import Cliente, Despesa, Documento, Oportunidade, Parcela, Tarefa, Venda


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "nome",
            "telefone",
            "email",
            "origem",
            "tipo_evento",
            "data_evento",
            "proxima_oportunidade",
            "observacoes",
        ]
        widgets = {
            "data_evento": DateInput(),
            "proxima_oportunidade": DateInput(),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class VendaForm(forms.ModelForm):
    primeira_parcela = forms.DateField(
        label="Vencimento da primeira parcela",
        required=False,
        widget=DateInput(),
    )

    class Meta:
        model = Venda
        fields = [
            "cliente",
            "titulo",
            "data_venda",
            "valor_total",
            "status",
            "forma_pagamento",
            "condicao_pagamento",
            "quantidade_parcelas",
            "primeira_parcela",
            "observacoes",
        ]
        widgets = {
            "data_venda": DateInput(),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class ParcelaForm(forms.ModelForm):
    class Meta:
        model = Parcela
        fields = ["numero", "valor", "vencimento", "data_pagamento", "status", "lembrete_em", "observacoes"]
        widgets = {
            "vencimento": DateInput(),
            "data_pagamento": DateInput(),
            "lembrete_em": DateInput(),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }


class DespesaForm(forms.ModelForm):
    class Meta:
        model = Despesa
        fields = ["descricao", "categoria", "valor", "data", "vencimento", "status", "forma_pagamento", "observacoes"]
        widgets = {
            "data": DateInput(),
            "vencimento": DateInput(),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class OportunidadeForm(forms.ModelForm):
    class Meta:
        model = Oportunidade
        fields = [
            "cliente",
            "nome_lead",
            "titulo",
            "tipo_evento",
            "valor_estimado",
            "etapa",
            "prioridade",
            "origem",
            "proximo_contato",
            "observacoes",
        ]
        widgets = {
            "proximo_contato": DateInput(),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class TarefaForm(forms.ModelForm):
    class Meta:
        model = Tarefa
        fields = ["cliente", "titulo", "tipo", "data", "hora", "status", "descricao"]
        widgets = {
            "data": DateInput(),
            "hora": forms.TimeInput(attrs={"type": "time"}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = [
            "cliente",
            "titulo",
            "status",
            "contato_whatsapp",
            "contato_email",
            "forma_envio",
            "enviado_em",
            "assinado_em",
            "data_limite",
            "conteudo_contrato",
            "observacoes",
        ]
        widgets = {
            "enviado_em": DateInput(),
            "assinado_em": DateInput(),
            "data_limite": DateInput(),
            "conteudo_contrato": forms.Textarea(attrs={"rows": 14}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }
