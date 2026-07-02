from datetime import timedelta
from decimal import Decimal
from string import Template

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


CONTRATO_FESTA_INFANTIL_TEMPLATE = """CONTRATO DE SERVICO

CONTRATADO: JOAO BOSCO FOTOGRAFIA
E-MAIL: JOAOBOSCOFOTOS@GMAIL.COM
TEL: (85) 98713-7641
CNPJ: 25.165.098/0001-68

CONTRATANTE: {{ cliente_nome }}
CPF: {{ cliente_cpf }}
ENDERECO: {{ cliente_endereco }}
TELEFONE: {{ cliente_telefone }}
E-MAIL: {{ cliente_email }}

NOME DO ANIVERSARIANTE: {{ aniversariante }}
IDADE: {{ idade }}
LOCAL: {{ local_evento }}
DATA: {{ data_evento }}
HORARIO: {{ horario_inicio }} as {{ horario_fim }}

DESCRICAO DO SERVICO:
{{ servico }}

VALOR TOTAL: R$ {{ valor }}
FORMA DE PAGAMENTO: {{ forma_pagamento }}
PARCELAS:
{{ parcelas }}

ADIANTAMENTO: R$ {{ adiantamento }}
RESTANTE: R$ {{ restante }}

OBS: PERMANENCIA DE ATE 03 HORAS NO EVENTO, INICIANDO A PARTIR DO HORARIO ESTABELECIDO ACIMA.

Sera executado um numero superior ao das fotos acima encomendadas, a fim de aumentar a opcao de escolha.

O CONTRATADO entregara o LINK com todas as fotos do evento para a escolha das imagens que irao para o album no prazo de 20 (vinte) dias uteis apos o evento. O CONTRATANTE tera o prazo de 10 (dez) dias uteis, apos o recebimento das provas, para informar ao CONTRATADO as fotos selecionadas para o album.

O CONTRATANTE tera um prazo de 12 meses, a contar a partir do recebimento das imagens, para informar a selecao de fotos que irao para o album. Caso ultrapasse o periodo estipulado, o valor sera reajustado de acordo com a tabela atual de precos.

O CONTRATANTE devera enviar, em documento escrito, para o CONTRATADO, a lista de fotos escolhidas, utilizando a numeracao e nomenclatura original dos arquivos de prova.

O CONTRATADO entregara os trabalhos, apos o evento, de acordo com as datas que seguem: fotos em LINK em 20 (vinte) dias uteis, sendo um LINK com 100 fotos tratadas e outro LINK com todas as imagens em alta resolucao; album em 45 (quarenta e cinco) dias uteis apos a devolucao das fotos ou projeto escolhido e aprovado pelo cliente.

Apos a entrega para verificacao e aprovacao do cliente, o mesmo tera 02 (dois) dias uteis para devolucao no caso de necessidade de correcao do projeto. Caso nao aconteca a devolucao no prazo estipulado, o produto final sera considerado aprovado pelo cliente.

O LINK com fotos em alta resolucao pertence a empresa, ficando a disposicao para novas reproducoes mediante remuneracao estabelecida entre cliente e empresa.

Os arquivos originais ficarao na empresa por 30 dias apos finalizar o contrato com o contratante.

Em caso de desistencia, nao sera devolvido o adiantamento pago.

O CONTRATANTE autoriza a utilizacao de sua imagem pelo CONTRATADO em seu portfolio ou redes sociais exclusivamente para fins de divulgacao de seu trabalho e sem fins comerciais.

({{ autoriza_uso_imagem_sim }}) SIM         ({{ autoriza_uso_imagem_nao }}) NAO

E por estarem justos e contratados, firmam o presente instrumento em duas vias iguais.

Fortaleza, {{ data_contrato }}

ASSINATURA DO CLIENTE: __________________________________________
JOAO BOSCO LISBOA DE MORAIS: ___________________________________
"""


class Empresa(models.Model):
    nome = models.CharField(max_length=160)
    documento = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class PerfilUsuario(models.Model):
    ROLE_CHOICES = [
        ("admin_master", "Admin master"),
        ("empresa_admin", "Admin da empresa"),
        ("empresa_usuario", "Usuario da empresa"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil_crm")
    empresa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True, related_name="usuarios")
    papel = models.CharField(max_length=20, choices=ROLE_CHOICES, default="empresa_usuario")
    ultimo_acesso = models.DateTimeField(null=True, blank=True)
    online_ate = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]

    @property
    def online(self):
        return bool(self.online_ate and self.online_ate >= timezone.now())

    @property
    def admin_master(self):
        return self.papel == "admin_master" or self.user.is_superuser

    def __str__(self):
        return f"{self.user.username} - {self.get_papel_display()}"


class AcessoUsuario(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="acessos_crm")
    empresa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True, related_name="acessos")
    caminho = models.CharField(max_length=220)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.user.username} - {self.caminho}"


class ContratoAdminEmpresa(models.Model):
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("pago", "Pago"),
        ("atrasado", "Atrasado"),
        ("cancelado", "Cancelado"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="contratos_admin")
    descricao = models.CharField(max_length=160, default="Mensalidade CRM")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    vencimento = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    data_pagamento = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["vencimento", "empresa__nome"]

    def __str__(self):
        return f"{self.empresa} - {self.descricao}"


class AdminCompromisso(models.Model):
    TIPO_CHOICES = [
        ("reuniao", "Reuniao"),
        ("cobranca", "Cobranca"),
        ("suporte", "Suporte"),
        ("tarefa", "Tarefa"),
    ]
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("concluida", "Concluida"),
        ("atrasada", "Atrasada"),
    ]

    titulo = models.CharField(max_length=160)
    empresa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True, related_name="compromissos_admin")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="tarefa")
    data = models.DateField()
    hora = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    descricao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data", "hora", "titulo"]

    def __str__(self):
        return self.titulo


class Cliente(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="clientes")
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

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="vendas")
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
        return sum((parcela.valor_recebido_efetivo for parcela in self.parcelas.all()), Decimal("0.00"))

    @property
    def valor_pendente(self):
        return max(self.valor_total - self.valor_pago, Decimal("0.00"))


class Parcela(models.Model):
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("parcial", "Parcial"),
        ("pago", "Pago"),
        ("atrasado", "Atrasado"),
    ]

    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="parcelas")
    numero = models.PositiveIntegerField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    valor_recebido = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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
    def valor_recebido_efetivo(self):
        if self.valor_recebido:
            return self.valor_recebido
        if self.status == "pago":
            return self.valor
        return Decimal("0.00")

    @property
    def valor_em_aberto(self):
        return max(self.valor - self.valor_recebido_efetivo, Decimal("0.00"))

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

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="despesas")
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

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="oportunidades")
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
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="oportunidades_perdidas")
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

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="eventos")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos")
    venda = models.OneToOneField(Venda, on_delete=models.SET_NULL, null=True, blank=True, related_name="evento")
    nome = models.CharField(max_length=160)
    tipo_evento = models.CharField(max_length=100, choices=TIPO_CHOICES, blank=True)
    data_festa = models.DateField(null=True, blank=True)
    horario = models.TimeField(null=True, blank=True)
    horario_fim = models.TimeField(null=True, blank=True)
    contato = models.CharField(max_length=80, blank=True)
    cpf_contratante = models.CharField(max_length=20, blank=True)
    endereco_contratante = models.CharField(max_length=220, blank=True)
    aniversariante = models.CharField(max_length=160, blank=True)
    idade = models.CharField(max_length=30, blank=True)
    local_evento = models.CharField(max_length=180, blank=True)
    em_buffet = models.BooleanField(default=False)
    descricao_servico = models.TextField(blank=True)
    valor_cobrado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    forma_pagamento = models.CharField(max_length=20, choices=Venda.FORMA_CHOICES, default="pix")
    pagamento_recebido = models.BooleanField(default=False)
    quantidade_parcelas = models.PositiveIntegerField(default=1)
    primeira_parcela = models.DateField(null=True, blank=True)
    adiantamento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adiantamento_pago = models.BooleanField(default=False)
    autoriza_uso_imagem = models.BooleanField(default=True)
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
                if parcela.status in ["pendente", "parcial", "atrasado"] and parcela.vencimento < timezone.localdate():
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
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="lembretes_anuais")
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

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="tarefas")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="tarefas")
    nome_contato = models.CharField(max_length=160, blank=True)
    evento = models.OneToOneField(
        "Evento",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="agenda_trabalho",
    )
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

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="documentos")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos")
    evento = models.ForeignKey(Evento, on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos")
    titulo = models.CharField(max_length=160)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="rascunho")
    contato_whatsapp = models.CharField(max_length=30, blank=True)
    contato_email = models.EmailField(blank=True)
    forma_envio = models.CharField(max_length=20, choices=ENVIO_CHOICES, default="ambos")
    enviado_em = models.DateField(null=True, blank=True)
    assinado_em = models.DateField(null=True, blank=True)
    data_limite = models.DateField(null=True, blank=True)
    conteudo_contrato = models.TextField(
        blank=True,
        default=CONTRATO_FESTA_INFANTIL_TEMPLATE,
    )
    arquivo_assinado = models.FileField(upload_to="documentos/assinados/", blank=True)
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
        evento = self.evento
        cliente_contato = " / ".join(filter(None, [self.contato_whatsapp, self.contato_email]))
        data_evento = ""
        if evento and evento.data_festa:
            data_evento = evento.data_festa.strftime("%d/%m/%Y")
        elif self.cliente and self.cliente.data_evento:
            data_evento = self.cliente.data_evento.strftime("%d/%m/%Y")
        servico = ""
        valor = ""
        forma_pagamento = ""
        parcelas = ""
        adiantamento = ""
        restante = ""
        if evento:
            servico = evento.descricao_servico or (evento.get_tipo_evento_display() if evento.tipo_evento else evento.nome)
            valor = f"{evento.valor_cobrado:.2f}".replace(".", ",")
            forma_pagamento = evento.get_forma_pagamento_display()
            if evento.adiantamento:
                adiantamento = f"{evento.adiantamento:.2f}".replace(".", ",")
            if evento.valor_cobrado:
                restante_valor = max(evento.valor_cobrado - evento.adiantamento, Decimal("0.00"))
                restante = f"{restante_valor:.2f}".replace(".", ",")
            if evento.venda_id:
                parcelas = "\n".join(
                    f"{parcela.numero}a Parcela - Valor R$ {parcela.valor:.2f} - Data {parcela.vencimento:%d/%m/%Y}".replace(".", ",")
                    for parcela in evento.venda.parcelas.all()
                )
            if not parcelas and evento.valor_cobrado:
                parcelas = f"1a Parcela - Valor R$ {valor} - Data {data_evento or '____/____/____'}"
        elif self.cliente:
            servico = self.cliente.tipo_evento
        contexto = {
            "cliente_nome": cliente_nome,
            "cliente_contato": cliente_contato,
            "cliente_cpf": evento.cpf_contratante if evento else "",
            "cliente_endereco": evento.endereco_contratante if evento else "",
            "cliente_telefone": self.contato_whatsapp or (self.cliente.telefone if self.cliente else ""),
            "cliente_email": self.contato_email or (self.cliente.email if self.cliente else ""),
            "servico": servico,
            "valor": valor,
            "data_evento": data_evento,
            "aniversariante": (evento.aniversariante or evento.nome) if evento else cliente_nome,
            "idade": evento.idade if evento else "",
            "local_evento": evento.local_evento if evento else "",
            "horario_inicio": evento.horario.strftime("%H:%M") if evento and evento.horario else "",
            "horario_fim": evento.horario_fim.strftime("%H:%M") if evento and evento.horario_fim else "",
            "forma_pagamento": forma_pagamento,
            "parcelas": parcelas,
            "adiantamento": adiantamento,
            "restante": restante,
            "autoriza_uso_imagem_sim": " X " if evento and evento.autoriza_uso_imagem else "   ",
            "autoriza_uso_imagem_nao": "   " if evento and evento.autoriza_uso_imagem else " X ",
            "data_contrato": timezone.localdate().strftime("%d/%m/%Y"),
        }
        texto = self.conteudo_contrato
        for chave, valor in contexto.items():
            texto = texto.replace("{{ " + chave + " }}", valor)
            texto = texto.replace("{{" + chave + "}}", valor)
        return Template(texto).safe_substitute(contexto)
