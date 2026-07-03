from calendar import monthrange
from decimal import Decimal
import unicodedata

from django import forms
from django.utils import timezone

from .models import (
    AdminCompromisso,
    Cliente,
    ContratoAdminEmpresa,
    Despesa,
    Documento,
    Empresa,
    Evento,
    LembreteAnual,
    Oportunidade,
    Parcela,
    Tarefa,
    Venda,
)


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


class EmpresaAdminForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["nome", "documento", "email", "telefone", "ativa"]


class ContratoAdminEmpresaForm(forms.ModelForm):
    valor = CurrencyField(max_digits=10, decimal_places=2, widget=forms.TextInput(attrs={"inputmode": "decimal"}))

    class Meta:
        model = ContratoAdminEmpresa
        fields = ["empresa", "descricao", "valor", "vencimento", "status", "data_pagamento", "observacoes"]
        widgets = {
            "vencimento": DateInput(),
            "data_pagamento": DateInput(),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class AdminCompromissoForm(forms.ModelForm):
    class Meta:
        model = AdminCompromisso
        fields = ["titulo", "empresa", "tipo", "data", "hora", "status", "descricao"]
        widgets = {
            "data": DateInput(),
            "hora": forms.TimeInput(attrs={"type": "time"}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }


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
        self.empresa = kwargs.pop("empresa", None)
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
    valor = CurrencyField(
        label="Valor contratado da parcela",
        max_digits=10,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00"}),
    )
    valor_recebido = CurrencyField(
        label="Valor recebido",
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00"}),
    )

    class Meta:
        model = Parcela
        fields = ["numero", "valor", "valor_recebido", "vencimento", "data_pagamento", "status", "lembrete_em", "observacoes"]
        widgets = {
            "vencimento": DateInput(),
            "data_pagamento": DateInput(),
            "lembrete_em": DateInput(),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        valor = cleaned_data.get("valor") or Decimal("0.00")
        valor_recebido = cleaned_data.get("valor_recebido") or Decimal("0.00")
        status = cleaned_data.get("status")
        if valor_recebido < 0:
            self.add_error("valor_recebido", "O valor recebido nao pode ser negativo.")
        if status in ["pendente", "atrasado"]:
            cleaned_data["valor_recebido"] = Decimal("0.00")
            cleaned_data["data_pagamento"] = None
        elif status == "pago" and (not valor_recebido or valor_recebido > valor):
            cleaned_data["valor_recebido"] = valor
        elif valor_recebido > valor and valor:
            self.add_error("valor_recebido", "O valor recebido nao pode ser maior que o valor contratado.")
        return cleaned_data

    def save(self, commit=True):
        parcela = super().save(commit=False)
        if not parcela.valor_recebido:
            parcela.valor_recebido = Decimal("0.00")
        if parcela.status in ["pendente", "atrasado"]:
            parcela.valor_recebido = Decimal("0.00")
            parcela.data_pagamento = None
        elif parcela.status == "pago":
            if parcela.valor and (not parcela.valor_recebido or parcela.valor_recebido > parcela.valor):
                parcela.valor_recebido = parcela.valor
            parcela.status = "pago"
            if not parcela.data_pagamento:
                parcela.data_pagamento = timezone.localdate()
        elif parcela.valor_recebido > 0:
            parcela.status = "parcial"
            if not parcela.data_pagamento:
                parcela.data_pagamento = timezone.localdate()
        elif parcela.status in ["pago", "parcial"]:
            parcela.status = "pendente"
            parcela.data_pagamento = None
        if commit:
            parcela.save()
            self.save_m2m()
        return parcela


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
        self.empresa = kwargs.pop("empresa", None)
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
    nome = forms.CharField(label="Nome completo do contratante", max_length=160)
    email = forms.EmailField(label="E-mail do contratante", required=False)
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
        label="Valor total contratado",
        max_digits=10,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00"}),
    )
    adiantamento = CurrencyField(
        label="Valor do adiantamento",
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00"}),
    )

    class Meta:
        model = Evento
        fields = [
            "nome",
            "email",
            "tipo_evento",
            "data_festa",
            "horario",
            "horario_fim",
            "contato",
            "cpf_contratante",
            "endereco_contratante",
            "aniversariante",
            "idade",
            "local_evento",
            "em_buffet",
            "descricao_servico",
            "valor_cobrado",
            "forma_pagamento",
            "pagamento_recebido",
            "quantidade_parcelas",
            "primeira_parcela",
            "adiantamento",
            "adiantamento_pago",
            "autoriza_uso_imagem",
            "observacoes",
        ]
        labels = {
            "tipo_evento": "Tipo do evento",
            "data_festa": "Data do evento",
            "horario": "Horario de inicio",
            "horario_fim": "Horario de termino",
            "contato": "Telefone do contratante",
            "cpf_contratante": "CPF do contratante",
            "endereco_contratante": "Endereco do contratante",
            "aniversariante": "Nome do aniversariante",
            "idade": "Idade do aniversariante",
            "local_evento": "Local do evento",
            "em_buffet": "Sera em buffet?",
            "descricao_servico": "Descricao do servico contratado",
            "valor_cobrado": "Valor cobrado",
            "forma_pagamento": "Forma de pagamento",
            "pagamento_recebido": "Pagamento ja recebido?",
            "quantidade_parcelas": "Quantidade de parcelas",
            "primeira_parcela": "Data do primeiro pagamento",
            "adiantamento_pago": "Pagamento adianto",
            "autoriza_uso_imagem": "Autoriza uso de imagem?",
            "observacoes": "Observacoes internas",
        }
        widgets = {
            "data_festa": DateInput(),
            "primeira_parcela": DateInput(),
            "horario": forms.TimeInput(attrs={"type": "time"}),
            "horario_fim": forms.TimeInput(attrs={"type": "time"}),
            "endereco_contratante": forms.TextInput(attrs={"placeholder": "Rua, numero, bairro, cidade"}),
            "descricao_servico": forms.Textarea(attrs={"rows": 4, "placeholder": "Descreva exatamente o servico contratado"}),
            "local_evento": forms.TextInput(attrs={"placeholder": "Ex: Buffet, igreja, salao, endereco"}),
            "quantidade_parcelas": forms.NumberInput(attrs={"min": 1, "max": 60}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop("empresa", None)
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance and instance.pk:
            self.fields["nome"].initial = instance.cliente.nome if instance.cliente else instance.nome
            self.fields["email"].initial = instance.cliente.email if instance.cliente else ""
            self.fields["tipo_evento"].initial = dict(Evento.TIPO_CHOICES).get(instance.tipo_evento, instance.tipo_evento)
            if not instance.valor_cobrado:
                self.fields["valor_cobrado"].initial = ""
            if not instance.adiantamento:
                self.fields["adiantamento"].initial = ""
        elif not self.is_bound:
            self.fields["valor_cobrado"].initial = ""
            self.fields["adiantamento"].initial = ""
        self.tipo_evento_opcoes = opcoes_tipo_evento()
        clientes = Cliente.objects.order_by("nome")
        if self.empresa:
            clientes = clientes.filter(empresa=self.empresa)
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
        self.fields["adiantamento_pago"].help_text = "Marque quando o adiantamento ja entrou no caixa."
        self.fields["quantidade_parcelas"].widget.attrs.update({"min": 1, "max": 60})

    def clean_tipo_evento(self):
        return valor_tipo_evento_digitado(self.cleaned_data.get("tipo_evento"))

    def _get_validation_exclusions(self):
        exclude = super()._get_validation_exclusions()
        exclude.add("tipo_evento")
        return exclude

    def clean(self):
        cleaned_data = super().clean()
        quantidade = cleaned_data.get("quantidade_parcelas") or 1
        if quantidade < 1:
            self.add_error("quantidade_parcelas", "Informe pelo menos 1 parcela.")
        valor_cobrado = cleaned_data.get("valor_cobrado") or Decimal("0.00")
        adiantamento = cleaned_data.get("adiantamento") or Decimal("0.00")
        cleaned_data["adiantamento"] = adiantamento
        if adiantamento > valor_cobrado:
            self.add_error("adiantamento", "O adiantamento nao pode ser maior que o valor cobrado.")
        if not adiantamento:
            cleaned_data["adiantamento_pago"] = False
        return cleaned_data

    def save(self, commit=True):
        evento = super().save(commit=False)
        nome = self.cleaned_data["nome"].strip()
        evento.nome = nome
        if not evento.adiantamento:
            evento.adiantamento = Decimal("0.00")
        if self.empresa:
            evento.empresa = self.empresa
        cliente_qs = Cliente.objects.filter(nome__iexact=nome)
        if self.empresa:
            cliente_qs = cliente_qs.filter(empresa=self.empresa)
        cliente = cliente_qs.first()
        if not cliente:
            cliente = Cliente(nome=nome, empresa=self.empresa)
        elif self.empresa and not cliente.empresa_id:
            cliente.empresa = self.empresa
        cliente.telefone = evento.contato or cliente.telefone
        cliente.email = self.cleaned_data.get("email") or cliente.email
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

    def criar_documento_evento(self, evento):
        if not evento.cliente_id:
            return None

        contato_whatsapp = evento.contato or evento.cliente.telefone
        documento, _ = Documento.objects.get_or_create(
            evento=evento,
            defaults={
                "empresa": evento.empresa,
                "cliente": evento.cliente,
                "titulo": f"Contrato - {evento.nome}",
                "status": "rascunho",
                "contato_whatsapp": contato_whatsapp,
                "contato_email": evento.cliente.email,
                "forma_envio": "ambos",
                "data_limite": evento.data_festa,
                "observacoes": "Documento criado automaticamente a partir do cadastro do evento.",
            },
        )
        return documento

    def sincronizar_venda(self, evento):
        if not evento.cliente_id or not evento.valor_cobrado:
            return None

        venda = evento.venda or Venda()
        venda.empresa = evento.empresa
        venda.cliente = evento.cliente
        venda.titulo = evento.tipo_evento or f"Evento - {evento.nome}"
        venda.valor_total = evento.valor_cobrado
        venda.forma_pagamento = evento.forma_pagamento
        tem_adiantamento = evento.adiantamento > 0
        quantidade_restante = max(evento.quantidade_parcelas, 1)
        total_parcelas = quantidade_restante + (1 if tem_adiantamento else 0)
        venda.condicao_pagamento = "parcelado" if total_parcelas > 1 else "avista"
        venda.quantidade_parcelas = total_parcelas
        venda.data_venda = venda.data_venda or timezone.localdate()
        pagamento_recebido = evento.pagamento_recebido and (
            total_parcelas == 1 or evento.forma_pagamento == "cartao"
        )
        venda.status = "pago" if pagamento_recebido else "pendente"
        venda.observacoes = evento.observacoes
        venda.save()

        if evento.venda_id != venda.pk:
            evento.venda = venda
            evento.save(update_fields=["venda", "atualizado_em"])

        valor_restante = max(evento.valor_cobrado - evento.adiantamento, Decimal("0.00"))
        valor_base = (valor_restante / quantidade_restante).quantize(Decimal("0.01"))
        restante = valor_restante
        parcelas_mantidas = []
        hoje = timezone.localdate()
        primeira_parcela = evento.primeira_parcela or hoje

        if tem_adiantamento:
            parcela = venda.parcelas.filter(numero=1).first() or Parcela(venda=venda, numero=1)
            parcela.valor = evento.adiantamento
            parcela.vencimento = primeira_parcela
            parcela.lembrete_em = primeira_parcela
            if evento.adiantamento_pago or evento.pagamento_recebido:
                parcela.valor_recebido = evento.adiantamento
                parcela.status = "pago"
                parcela.data_pagamento = primeira_parcela
            else:
                parcela.valor_recebido = Decimal("0.00")
                parcela.status = "pendente"
                parcela.data_pagamento = None
            parcela.observacoes = "Adiantamento informado no formulario de contrato do evento."
            parcela.save()
            parcelas_mantidas.append(parcela.pk)

        deslocamento = 1 if tem_adiantamento else 0
        for numero in range(1, quantidade_restante + 1):
            numero_parcela = numero + deslocamento
            parcela = venda.parcelas.filter(numero=numero_parcela).first() or Parcela(venda=venda, numero=numero_parcela)
            valor = valor_base if numero < quantidade_restante else restante
            parcela.valor = valor
            parcela.vencimento = add_months(primeira_parcela, numero - 1 + deslocamento)
            parcela.lembrete_em = parcela.vencimento
            if pagamento_recebido:
                parcela.valor_recebido = valor
                parcela.status = "pago"
                parcela.data_pagamento = hoje
            else:
                parcela.valor_recebido = Decimal("0.00")
                parcela.status = "pendente"
                parcela.data_pagamento = None
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
                "empresa": evento.empresa,
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
        fields = ["cliente", "nome_contato", "evento", "titulo", "tipo", "data", "hora", "status", "descricao"]
        labels = {
            "nome_contato": "Nome avulso",
        }
        widgets = {
            "data": DateInput(),
            "hora": forms.TimeInput(attrs={"type": "time"}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].required = False
        self.fields["evento"].required = False
        self.fields["nome_contato"].required = False
        self.fields["nome_contato"].help_text = "Use para visitas, reunioes ou compromissos com pessoas fora do cadastro."
        self.fields["nome_contato"].widget.attrs.update(
            {
                "placeholder": "Ex: Visita tecnica, fornecedor, reuniao externa",
                "autocomplete": "off",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get("cliente")
        evento = cleaned_data.get("evento")
        nome_contato = (cleaned_data.get("nome_contato") or "").strip()
        if evento:
            cleaned_data["cliente"] = evento.cliente
            cleaned_data["nome_contato"] = ""
        elif not cliente and not nome_contato:
            self.add_error("nome_contato", "Informe um cliente cadastrado ou um nome avulso.")
        return cleaned_data


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = [
            "cliente",
            "evento",
            "titulo",
            "status",
            "contato_whatsapp",
            "contato_email",
            "forma_envio",
            "enviado_em",
            "assinado_em",
            "data_limite",
            "conteudo_contrato",
            "arquivo_assinado",
            "observacoes",
        ]
        widgets = {
            "enviado_em": DateInput(),
            "assinado_em": DateInput(),
            "data_limite": DateInput(),
            "conteudo_contrato": forms.Textarea(
                attrs={
                    "rows": 30,
                    "class": "contract-editor",
                    "spellcheck": "true",
                }
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }
