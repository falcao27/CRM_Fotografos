from datetime import timedelta
from decimal import Decimal
from string import Template

from django.db import models
from django.utils import timezone


class Cliente(models.Model):
    nome = models.CharField(max_length=160)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    origem = models.CharField(max_length=80, blank=True)
    tipo_evento = models.CharField(max_length=100, blank=True)
    data_evento = models.DateField(null=True, blank=True)
    proxima_oportunidade = models.DateField(
        null=True,
        blank=True,
        help_text="Data prevista para tentar uma nova venda.",
    )
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def data_alerta_recompra(self):
        return self.proxima_oportunidade

    @property
    def precisa_alerta_recompra(self):
        return bool(self.proxima_oportunidade and self.proxima_oportunidade <= timezone.localdate())


class Venda(models.Model):
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("pago", "Pago"),
        ("atrasado", "Atrasado"),
        ("cancelado", "Cancelado"),
    ]
    FORMA_CHOICES = [
        ("pix", "Pix"),
        ("dinheiro", "Dinheiro"),
        ("boleto", "Boleto"),
        ("cartao", "Cartao"),
        ("transferencia", "Transferencia"),
        ("outro", "Outro"),
    ]
    CONDICAO_CHOICES = [
        ("avista", "A vista"),
        ("parcelado", "Parcelado"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="vendas")
    titulo = models.CharField(max_length=160)
    data_venda = models.DateField(default=timezone.localdate)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    forma_pagamento = models.CharField(max_length=20, choices=FORMA_CHOICES, default="pix")
    condicao_pagamento = models.CharField(max_length=20, choices=CONDICAO_CHOICES, default="avista")
    quantidade_parcelas = models.PositiveIntegerField(default=1)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_venda", "-id"]

    def __str__(self):
        return f"{self.titulo} - {self.cliente}"

    @property
    def valor_pago(self):
        pago = self.parcelas.filter(status="pago").aggregate(total=models.Sum("valor"))["total"]
        return pago or Decimal("0.00")

    @property
    def valor_pendente(self):
        return max(self.valor_total - self.valor_pago, Decimal("0.00"))


class Parcela(models.Model):
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("pago", "Pago"),
        ("atrasado", "Atrasado"),
    ]

    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="parcelas")
    numero = models.PositiveIntegerField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    lembrete_em = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["vencimento", "numero"]
        unique_together = ["venda", "numero"]

    def __str__(self):
        return f"Parcela {self.numero} - {self.venda}"

    @property
    def deve_alertar(self):
        hoje = timezone.localdate()
        if self.status == "pago":
            return False
        if self.vencimento < hoje:
            return True
        return bool(self.lembrete_em and self.lembrete_em <= hoje)

    @property
    def status_financeiro(self):
        if self.status != "pago" and self.vencimento < timezone.localdate():
            return "vencido"
        return self.status

    @property
    def status_financeiro_label(self):
        if self.status_financeiro == "vencido":
            return "Vencido"
        return self.get_status_display()


class Despesa(models.Model):
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("pago", "Pago"),
        ("atrasado", "Atrasado"),
    ]
    FORMA_CHOICES = Venda.FORMA_CHOICES

    descricao = models.CharField(max_length=160)
    categoria = models.CharField(max_length=90, blank=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField(default=timezone.localdate)
    vencimento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    forma_pagamento = models.CharField(max_length=20, choices=FORMA_CHOICES, default="pix")
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-id"]

    def __str__(self):
        return self.descricao


class Oportunidade(models.Model):
    ETAPA_CHOICES = [
        ("novo", "Novo lead"),
        ("orcamento", "Orcamento"),
        ("negociacao", "Negociacao"),
        ("fechado", "Fechado"),
        ("perdido", "Perdido"),
    ]
    PRIORIDADE_CHOICES = [
        ("baixa", "Baixa"),
        ("media", "Media"),
        ("alta", "Alta"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="oportunidades")
    nome_lead = models.CharField(max_length=160)
    titulo = models.CharField(max_length=160)
    nome_indicacao = models.CharField(max_length=160, blank=True)
    tipo_evento = models.CharField(max_length=100, blank=True)
    valor_estimado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_negociado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    etapa = models.CharField(max_length=20, choices=ETAPA_CHOICES, default="novo")
    prioridade = models.CharField(max_length=20, choices=PRIORIDADE_CHOICES, default="media")
    origem = models.CharField(max_length=90, blank=True)
    proximo_contato = models.DateField(null=True, blank=True)
    data_festa = models.DateField(null=True, blank=True)
    horario = models.TimeField(null=True, blank=True)
    contato = models.CharField(max_length=80, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["etapa", "-valor_estimado", "nome_lead"]

    def __str__(self):
        return f"{self.nome_lead} - {self.titulo}"

    @property
    def valor_em_vigor(self):
        if self.etapa in ["negociacao", "fechado"] and self.valor_negociado is not None:
            return self.valor_negociado
        return self.valor_estimado


class OportunidadePerdida(models.Model):
    oportunidade = models.OneToOneField(
        Oportunidade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registro_perdido",
    )
    nome = models.CharField(max_length=160)
    tipo_prospeccao = models.CharField(max_length=160, blank=True)
    nome_indicacao = models.CharField(max_length=160, blank=True)
    tipo_evento = models.CharField(max_length=100, blank=True)
    data_festa = models.DateField(null=True, blank=True)
    horario = models.TimeField(null=True, blank=True)
    contato = models.CharField(max_length=80, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-atualizado_em", "nome"]

    def __str__(self):
        return self.nome


class Evento(models.Model):
    TIPO_CHOICES = [
        ("casamento", "Casamento"),
        ("pre_wedding", "Pre-wedding"),
        ("ensaio_casal", "Ensaio de casal"),
        ("ensaio_familia", "Ensaio de familia"),
        ("gestante", "Gestante"),
        ("newborn", "Newborn"),
        ("acompanhamento_bebe", "Acompanhamento de bebe"),
        ("batizado", "Batizado"),
        ("aniversario", "Aniversario"),
        ("aniversario_infantil", "Aniversario infantil"),
        ("debutante", "15 anos / debutante"),
        ("formatura", "Formatura"),
        ("corporativo", "Corporativo"),
        ("evento_social", "Evento social"),
        ("evento_religioso", "Evento religioso"),
        ("ensaio_feminino", "Ensaio feminino"),
        ("ensaio_masculino", "Ensaio masculino"),
        ("retrato_profissional", "Retrato profissional"),
        ("branding", "Branding pessoal"),
        ("produto", "Produto"),
        ("imobiliario", "Imobiliario"),
        ("esportivo", "Esportivo"),
        ("pet", "Pet"),
        ("outro", "Outro"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos")
    venda = models.OneToOneField(Venda, on_delete=models.SET_NULL, null=True, blank=True, related_name="evento")
    nome = models.CharField(max_length=160)
    tipo_evento = models.CharField(max_length=100, choices=TIPO_CHOICES, blank=True)
    data_festa = models.DateField(null=True, blank=True)
    horario = models.TimeField(null=True, blank=True)
    contato = models.CharField(max_length=80, blank=True)
    valor_cobrado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    forma_pagamento = models.CharField(max_length=20, choices=Venda.FORMA_CHOICES, default="pix")
    pagamento_recebido = models.BooleanField(default=False)
    quantidade_parcelas = models.PositiveIntegerField(default=1)
    primeira_parcela = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_festa", "horario", "nome"]

    def __str__(self):
        return f"{self.nome} - {self.get_tipo_evento_display() if self.tipo_evento else 'Evento'}"

    @property
    def pagamento_status(self):
        if self.pagamento_recebido or (self.venda_id and self.venda.status == "pago"):
            return "pago"
        if self.venda_id:
            for parcela in self.venda.parcelas.all():
                if parcela.status in ["pendente", "atrasado"] and parcela.vencimento < timezone.localdate():
                    return "vencido"
        return "pendente"

    @property
    def pagamento_status_label(self):
        labels = {
            "pago": "Pago",
            "vencido": "Vencido",
            "pendente": "A receber",
        }
        return labels[self.pagamento_status]


class LembreteAnual(models.Model):
    evento = models.OneToOneField(Evento, on_delete=models.CASCADE, related_name="lembrete_anual")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="lembretes_anuais")
    nome = models.CharField(max_length=160)
    contato = models.CharField(max_length=80, blank=True)
    data_original = models.DateField()
    data_proximo_evento = models.DateField()
    data_alerta = models.DateField()
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_alerta", "nome"]

    def __str__(self):
        return f"{self.nome} - {self.data_proximo_evento:%d/%m/%Y}"

    @property
    def ativo(self):
        hoje = timezone.localdate()
        return self.data_alerta <= hoje <= self.data_proximo_evento


class Tarefa(models.Model):
    TIPO_CHOICES = [
        ("trabalho", "Trabalho"),
        ("tarefa", "Tarefa"),
        ("pagamento", "Pagamento"),
        ("reuniao", "Reuniao"),
        ("entrega", "Entrega"),
        ("lembrete", "Lembrete"),
    ]
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("concluida", "Concluida"),
        ("atrasada", "Atrasada"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="tarefas")
    titulo = models.CharField(max_length=160)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="tarefa")
    data = models.DateField(default=timezone.localdate)
    hora = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    descricao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data", "hora", "titulo"]

    def __str__(self):
        return self.titulo


class Documento(models.Model):
    STATUS_CHOICES = [
        ("rascunho", "Rascunho"),
        ("enviado", "Enviado para assinatura"),
        ("pendente", "Pendente de assinatura"),
        ("assinado", "Assinado"),
        ("vencido", "Vencido"),
    ]
    ENVIO_CHOICES = [
        ("whatsapp", "WhatsApp"),
        ("email", "E-mail"),
        ("ambos", "WhatsApp e e-mail"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos")
    titulo = models.CharField(max_length=160)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    contato_whatsapp = models.CharField(max_length=30, blank=True)
    contato_email = models.EmailField(blank=True)
    forma_envio = models.CharField(max_length=20, choices=ENVIO_CHOICES, default="whatsapp")
    enviado_em = models.DateField(null=True, blank=True)
    assinado_em = models.DateField(null=True, blank=True)
    data_limite = models.DateField(null=True, blank=True)
    conteudo_contrato = models.TextField(
        blank=True,
        default=(
            "CONTRATO DE PRESTACAO DE SERVICOS FOTOGRAFICOS\n\n"
            "Cliente: {{ cliente_nome }}\n"
            "Contato: {{ cliente_contato }}\n"
            "Servico contratado: {{ servico }}\n"
            "Valor: R$ {{ valor }}\n"
            "Data do evento: {{ data_evento }}\n\n"
            "O presente contrato define prazos, entrega dos arquivos, forma de pagamento "
            "e autorizacao de uso de imagem conforme combinado entre as partes.\n\n"
            "Assinatura do cliente: ______________________________\n"
            "Assinatura do fotografo: ____________________________"
        ),
    )
    observacoes = models.TextField(blank=True)
    ultimo_envio_em = models.DateTimeField(null=True, blank=True)
    ultimo_envio_sucesso = models.BooleanField(default=False)
    ultimo_envio_retorno = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "data_limite", "titulo"]

    def __str__(self):
        return self.titulo

    def contrato_renderizado(self):
        cliente_nome = self.cliente.nome if self.cliente else ""
        cliente_contato = " / ".join(filter(None, [self.contato_whatsapp, self.contato_email]))
        data_evento = self.cliente.data_evento.strftime("%d/%m/%Y") if self.cliente and self.cliente.data_evento else ""
        servico = self.cliente.tipo_evento if self.cliente else ""
        contexto = {
            "cliente_nome": cliente_nome,
            "cliente_contato": cliente_contato,
            "servico": servico,
            "valor": "",
            "data_evento": data_evento,
        }
        texto = self.conteudo_contrato
        for chave, valor in contexto.items():
            texto = texto.replace("{{ " + chave + " }}", valor)
            texto = texto.replace("{{" + chave + "}}", valor)
        return Template(texto).safe_substitute(contexto)
