from calendar import monthrange
from decimal import Decimal
import unicodedata

from django import forms
from django.utils import timezone

from .models import Cliente, Despesa, Documento, Evento, LembreteAnual, Oportunidade, Parcela, Tarefa, Venda


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)


class CurrencyField(forms.DecimalField):
    def prepare_value(self, value):
        if isinstance(value, Decimal):
            return f"{value:.2f}".replace(".", ",")
        return super().prepare_value(value)

    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip()
            if "," in value:
                value = value.replace(".", "").replace(",", ".")
            elif value.count(".") > 1:
                partes = value.split(".")
                value = "".join(partes[:-1]) + "." + partes[-1]
        return super().to_python(value)


def add_months(data, meses):
    mes = data.month - 1 + meses
    ano = data.year + mes // 12
    mes = mes % 12 + 1
    dia = min(data.day, monthrange(ano, mes)[1])
    return data.replace(year=ano, month=mes, day=dia)


def calcular_proxima_oportunidade(data_evento):
    if not data_evento:
        return None
    return add_months(add_months(data_evento, 12), -2)


def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", (valor or "").strip().lower())
    return "".join(caractere for caractere in texto if not unicodedata.combining(caractere))


def opcoes_tipo_evento():
    opcoes = []
    vistos = set()
    labels_fixos = dict(Evento.TIPO_CHOICES)

    for valor, label in Evento.TIPO_CHOICES:
        chave = normalizar_texto(label)
        if chave not in vistos:
            opcoes.append(label)
            vistos.add(chave)
        vistos.add(normalizar_texto(valor))

    tipos_salvos = (
        Evento.objects.exclude(tipo_evento="")
        .order_by("tipo_evento")
        .values_list("tipo_evento", flat=True)
        .distinct()
    )
    for tipo in tipos_salvos:
        label = labels_fixos.get(tipo, tipo)
        chave = normalizar_texto(label)
        if chave and chave not in vistos:
            opcoes.append(label)
            vistos.add(chave)
    return opcoes


def valor_tipo_evento_digitado(valor):
    valor = (valor or "").strip()
    if not valor:
        return ""
    chave_digitada = normalizar_texto(valor)
    for codigo, label in Evento.TIPO_CHOICES:
        if chave_digitada in {normalizar_texto(codigo), normalizar_texto(label)}:
            return codigo
    return valor


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proxima_oportunidade"].widget.attrs["readonly"] = "readonly"

    def save(self, commit=True):
        cliente = super().save(commit=False)
        if cliente.data_evento:
            cliente.proxima_oportunidade = calcular_proxima_oportunidade(cliente.data_evento)
        if commit:
            cliente.save()
            self.save_m2m()
        return cliente


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
    nome = forms.CharField(label="Nome", max_length=160)
    titulo = forms.ChoiceField(
        label="Tipo de prospecção",
        choices=[
            ("Instagram", "Instagram"),
            ("WhatsApp", "WhatsApp"),
            ("Site", "Site"),
            ("Indicacao", "Indicação"),
        ],
    )

    valor_estimado = CurrencyField(
        label="Valor do orcamento",
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00"}),
    )
    valor_negociado = CurrencyField(
        label="Valor em negociacao",
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00"}),
    )

    class Meta:
        model = Oportunidade
        fields = [
            "nome",
            "titulo",
            "nome_indicacao",
            "tipo_evento",
            "etapa",
            "valor_estimado",
            "valor_negociado",
            "data_festa",
            "horario",
            "contato",
            "observacoes",
        ]
        labels = {
            "nome_indicacao": "Nome de quem indicou",
            "tipo_evento": "Tipo do evento",
            "data_festa": "Data festa",
            "horario": "Horario",
            "contato": "Contato",
            "observacoes": "Observacao",
        }
        widgets = {
            "data_festa": DateInput(),
            "horario": forms.TimeInput(attrs={"type": "time"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance and instance.pk:
            self.fields["nome"].initial = instance.nome_lead
            valores = {valor for valor, _ in self.fields["titulo"].choices}
            if instance.titulo and instance.titulo not in valores:
                self.fields["titulo"].choices = [(instance.titulo, instance.titulo)] + list(self.fields["titulo"].choices)
        self.fields["nome"].widget.attrs.update({"placeholder": "Digite o nome do novo lead", "autocomplete": "off"})

    def save(self, commit=True):
        oportunidade = super().save(commit=False)
        nome = self.cleaned_data["nome"].strip()
        nome_indicacao = self.cleaned_data.get("nome_indicacao", "").strip()
        oportunidade.nome_lead = nome
        oportunidade.nome_indicacao = nome_indicacao
        oportunidade.cliente = None
        if oportunidade.valor_estimado is None:
            oportunidade.valor_estimado = Decimal("0.00")
        oportunidade.origem = (
            f"Indicação - {nome_indicacao}" if oportunidade.titulo == "Indicacao" and nome_indicacao else oportunidade.titulo
        )
        if commit:
            oportunidade.save()
            self.save_m2m()
        return oportunidade

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("titulo") == "Indicacao" and not cleaned_data.get("nome_indicacao"):
            self.add_error("nome_indicacao", "Informe o nome de quem indicou.")
        etapa = cleaned_data.get("etapa")
        valor_estimado = cleaned_data.get("valor_estimado")
        valor_negociado = cleaned_data.get("valor_negociado")
        if etapa in ["orcamento", "negociacao"] and not valor_estimado:
            self.add_error("valor_estimado", "Informe o valor do orcamento.")
        if etapa == "negociacao" and not valor_negociado:
            self.add_error("valor_negociado", "Informe o valor em negociacao.")
        return cleaned_data


class ReuniaoLeadForm(forms.Form):
    dia = forms.DateField(label="Dia", widget=DateInput())
    hora = forms.TimeField(label="Hora", widget=forms.TimeInput(attrs={"type": "time"}))
    local = forms.CharField(label="Local", max_length=180)


class EventoForm(forms.ModelForm):
    nome = forms.CharField(label="Nome", max_length=160)
    tipo_evento = forms.CharField(
        label="Tipo do evento",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "list": "tipos-evento-cadastrados",
                "placeholder": "Digite ou escolha um tipo de evento",
                "autocomplete": "off",
            }
        ),
    )
    valor_cobrado = CurrencyField(
        label="Valor cobrado",
        max_digits=10,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00"}),
    )

    class Meta:
        model = Evento
        fields = [
            "nome",
            "tipo_evento",
            "data_festa",
            "horario",
            "contato",
            "local_evento",
            "em_buffet",
            "valor_cobrado",
            "forma_pagamento",
            "pagamento_recebido",
            "quantidade_parcelas",
            "primeira_parcela",
            "observacoes",
        ]
        labels = {
            "tipo_evento": "Tipo do evento",
            "data_festa": "Data festa",
            "horario": "Horario",
            "contato": "Contato",
            "local_evento": "Local do evento",
            "em_buffet": "Sera em buffet?",
            "valor_cobrado": "Valor cobrado",
            "forma_pagamento": "Forma de pagamento",
            "pagamento_recebido": "Valor ja foi pago?",
            "quantidade_parcelas": "Quantas vezes",
            "primeira_parcela": "Data do primeiro pagamento",
            "observacoes": "Observacao",
        }
        widgets = {
            "data_festa": DateInput(),
            "primeira_parcela": DateInput(),
            "horario": forms.TimeInput(attrs={"type": "time"}),
            "local_evento": forms.TextInput(attrs={"placeholder": "Ex: Buffet, igreja, salao, endereco"}),
            "quantidade_parcelas": forms.NumberInput(attrs={"min": 1, "max": 60}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance and instance.pk:
            self.fields["nome"].initial = instance.cliente.nome if instance.cliente else instance.nome
            self.fields["tipo_evento"].initial = dict(Evento.TIPO_CHOICES).get(instance.tipo_evento, instance.tipo_evento)
        self.tipo_evento_opcoes = opcoes_tipo_evento()
        clientes = Cliente.objects.order_by("nome")
        vistos = set()
        self.clientes_opcoes = []
        for cliente in clientes:
            chave = cliente.nome.strip().lower()
            if not chave or chave in vistos:
                continue
            vistos.add(chave)
            self.clientes_opcoes.append(cliente)
        self.fields["nome"].widget.attrs.update(
            {
                "list": "clientes-cadastrados",
                "placeholder": "Digite para buscar ou cadastrar novo cliente",
                "autocomplete": "off",
            }
        )
        self.fields["nome"].help_text = "Digite parte do nome para filtrar clientes cadastrados ou informe um nome novo."
        self.fields["pagamento_recebido"].help_text = "Marque quando o valor ja entrou no caixa."
        self.fields["quantidade_parcelas"].widget.attrs.update({"min": 1, "max": 60})

    def clean_tipo_evento(self):
        return valor_tipo_evento_digitado(self.cleaned_data.get("tipo_evento"))

    def _get_validation_exclusions(self):
        exclude = super()._get_validation_exclusions()
        exclude.add("tipo_evento")
        return exclude

    def clean(self):
        cleaned_data = super().clean()
        forma_pagamento = cleaned_data.get("forma_pagamento")
        quantidade = cleaned_data.get("quantidade_parcelas") or 1
        if forma_pagamento not in {"boleto", "cartao"}:
            cleaned_data["quantidade_parcelas"] = 1
        elif quantidade < 1:
            self.add_error("quantidade_parcelas", "Informe pelo menos 1 parcela.")
        return cleaned_data

    def save(self, commit=True):
        evento = super().save(commit=False)
        nome = self.cleaned_data["nome"].strip()
        evento.nome = nome
        if evento.forma_pagamento not in {"boleto", "cartao"}:
            evento.quantidade_parcelas = 1
        cliente = Cliente.objects.filter(nome__iexact=nome).first()
        if not cliente:
            cliente = Cliente(nome=nome)
        cliente.telefone = evento.contato or cliente.telefone
        cliente.tipo_evento = evento.tipo_evento or cliente.tipo_evento
        cliente.data_evento = evento.data_festa or cliente.data_evento
        if cliente.data_evento:
            cliente.proxima_oportunidade = calcular_proxima_oportunidade(cliente.data_evento)
        cliente.observacoes = evento.observacoes or cliente.observacoes
        if commit:
            cliente.save()
            evento.cliente = cliente
            evento.save()
            self.sincronizar_venda(evento)
            self.sincronizar_lembrete_anual(evento)
            self.save_m2m()
        else:
            evento.cliente = cliente
        return evento

    def sincronizar_venda(self, evento):
        if not evento.cliente_id or not evento.valor_cobrado:
            return None

        venda = evento.venda or Venda()
        venda.cliente = evento.cliente
        venda.titulo = evento.tipo_evento or f"Evento - {evento.nome}"
        venda.valor_total = evento.valor_cobrado
        venda.forma_pagamento = evento.forma_pagamento
        venda.condicao_pagamento = "parcelado" if evento.quantidade_parcelas > 1 else "avista"
        venda.quantidade_parcelas = evento.quantidade_parcelas
        venda.data_venda = venda.data_venda or timezone.localdate()
        pagamento_recebido = evento.pagamento_recebido and (
            evento.quantidade_parcelas == 1 or evento.forma_pagamento == "cartao"
        )
        venda.status = "pago" if pagamento_recebido else "pendente"
        venda.observacoes = evento.observacoes
        venda.save()

        if evento.venda_id != venda.pk:
            evento.venda = venda
            evento.save(update_fields=["venda", "atualizado_em"])

        quantidade = max(evento.quantidade_parcelas, 1)
        valor_base = (evento.valor_cobrado / quantidade).quantize(Decimal("0.01"))
        restante = evento.valor_cobrado
        parcelas_mantidas = []
        hoje = timezone.localdate()
        primeira_parcela = evento.primeira_parcela or hoje
        for numero in range(1, quantidade + 1):
            parcela = venda.parcelas.filter(numero=numero).first() or Parcela(venda=venda, numero=numero)
            valor = valor_base if numero < quantidade else restante
            parcela.valor = valor
            parcela.vencimento = add_months(primeira_parcela, numero - 1)
            parcela.lembrete_em = parcela.vencimento
            parcela.status = "pago" if pagamento_recebido else "pendente"
            parcela.data_pagamento = hoje if parcela.status == "pago" else None
            parcela.observacoes = "Gerada automaticamente pelo cadastro do evento."
            parcela.save()
            parcelas_mantidas.append(parcela.pk)
            restante -= valor
        venda.parcelas.exclude(pk__in=parcelas_mantidas).delete()
        return venda

    def sincronizar_lembrete_anual(self, evento):
        if evento.tipo_evento not in {"aniversario", "aniversario_infantil"} or not evento.data_festa:
            LembreteAnual.objects.filter(evento=evento).delete()
            return None

        data_proximo_evento = add_months(evento.data_festa, 12)
        data_alerta = add_months(data_proximo_evento, -2)
        lembrete, _ = LembreteAnual.objects.update_or_create(
            evento=evento,
            defaults={
                "cliente": evento.cliente,
                "nome": evento.nome,
                "contato": evento.contato,
                "data_original": evento.data_festa,
                "data_proximo_evento": data_proximo_evento,
                "data_alerta": data_alerta,
                "observacoes": evento.observacoes,
            },
        )
        return lembrete


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
