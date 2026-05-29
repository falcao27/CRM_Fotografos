import csv
import io
import unicodedata
import zipfile
from calendar import Calendar, monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from html import escape
from xml.etree import ElementTree as ET

from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Case, Count, DecimalField, F, Q, Sum, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    ClienteForm,
    DespesaForm,
    DocumentoForm,
    EventoForm,
    OportunidadeForm,
    ParcelaForm,
    ReuniaoLeadForm,
    TarefaForm,
    VendaForm,
)
from .models import Cliente, Despesa, Documento, Evento, LembreteAnual, Oportunidade, OportunidadePerdida, Parcela, Tarefa, Venda
from .pdf import gerar_pdf_documento, nome_pdf_documento
from .services import EnvioDocumentoError, enviar_documento, link_whatsapp_manual


MESES_PT = [
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

CLIENTE_PLANILHA_CAMPOS = [
    ("nome", "Nome"),
    ("telefone", "Telefone"),
    ("email", "Email"),
    ("origem", "Origem"),
    ("tipo_evento", "Tipo de evento"),
    ("data_evento", "Data do evento"),
    ("proxima_oportunidade", "Proxima oportunidade"),
    ("observacoes", "Observacoes"),
]


def add_months(data, meses):
    mes = data.month - 1 + meses
    ano = data.year + mes // 12
    mes = mes % 12 + 1
    dia = min(data.day, monthrange(ano, mes)[1])
    return data.replace(year=ano, month=mes, day=dia)


def gerar_parcelas(venda, primeira_parcela):
    venda.parcelas.all().delete()
    quantidade = max(venda.quantidade_parcelas, 1)
    valor_base = (venda.valor_total / quantidade).quantize(Decimal("0.01"))
    restante = venda.valor_total

    for numero in range(1, quantidade + 1):
        valor = valor_base if numero < quantidade else restante
        vencimento = add_months(primeira_parcela, numero - 1)
        Parcela.objects.create(
            venda=venda,
            numero=numero,
            valor=valor,
            vencimento=vencimento,
            lembrete_em=vencimento - timedelta(days=3),
            status="pago" if venda.status == "pago" else "pendente",
            data_pagamento=venda.data_venda if venda.status == "pago" else None,
        )
        restante -= valor


def formatar_data_planilha(valor):
    return valor.strftime("%d/%m/%Y") if valor else ""


def ler_data_planilha(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        serial_excel = float(valor)
        if serial_excel > 59:
            return date(1899, 12, 30) + timedelta(days=int(serial_excel))
    except ValueError:
        pass
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return date.fromisoformat(valor) if formato == "%Y-%m-%d" else datetime.strptime(valor, formato).date()
        except ValueError:
            continue
    return None


def coluna_excel(indice):
    nome = ""
    while indice:
        indice, resto = divmod(indice - 1, 26)
        nome = chr(65 + resto) + nome
    return nome


def indice_coluna_excel(referencia):
    letras = "".join(caractere for caractere in referencia if caractere.isalpha())
    indice = 0
    for caractere in letras:
        indice = indice * 26 + (ord(caractere.upper()) - 64)
    return max(indice - 1, 0)


def montar_xlsx_clientes(clientes):
    linhas = [[rotulo for _, rotulo in CLIENTE_PLANILHA_CAMPOS]]
    for cliente in clientes:
        linhas.append(
            [
                cliente.nome,
                cliente.telefone,
                cliente.email,
                cliente.origem,
                cliente.tipo_evento,
                formatar_data_planilha(cliente.data_evento),
                formatar_data_planilha(cliente.proxima_oportunidade),
                cliente.observacoes,
            ]
        )

    linhas_xml = []
    for numero_linha, linha in enumerate(linhas, start=1):
        celulas = []
        for numero_coluna, valor in enumerate(linha, start=1):
            referencia = f"{coluna_excel(numero_coluna)}{numero_linha}"
            celulas.append(f'<c r="{referencia}" t="inlineStr"><is><t>{escape(str(valor or ""))}</t></is></c>')
        linhas_xml.append(f'<row r="{numero_linha}">{"".join(celulas)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(linhas_xml)}</sheetData>'
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Clientes" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    arquivo = io.BytesIO()
    with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED) as planilha:
        planilha.writestr("[Content_Types].xml", content_types)
        planilha.writestr("_rels/.rels", rels)
        planilha.writestr("xl/workbook.xml", workbook_xml)
        planilha.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        planilha.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return arquivo.getvalue()


def ler_linhas_xlsx(arquivo):
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(arquivo) as planilha:
        compartilhadas = []
        if "xl/sharedStrings.xml" in planilha.namelist():
            shared_root = ET.fromstring(planilha.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("x:si", ns):
                compartilhadas.append("".join(texto.text or "" for texto in item.findall(".//x:t", ns)))
        sheet_root = ET.fromstring(planilha.read("xl/worksheets/sheet1.xml"))
        linhas = []
        for row in sheet_root.findall(".//x:sheetData/x:row", ns):
            valores = []
            for cell in row.findall("x:c", ns):
                indice = indice_coluna_excel(cell.attrib.get("r", ""))
                while len(valores) < indice:
                    valores.append("")
                tipo = cell.attrib.get("t")
                valor = ""
                if tipo == "inlineStr":
                    valor = "".join(texto.text or "" for texto in cell.findall(".//x:t", ns))
                else:
                    node = cell.find("x:v", ns)
                    if node is not None and node.text is not None:
                        valor = compartilhadas[int(node.text)] if tipo == "s" else node.text
                valores.append(valor)
            linhas.append(valores)
    return linhas


def ler_linhas_csv(arquivo):
    texto = arquivo.read().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(texto)))


def normalizar_cabecalho(valor):
    texto = unicodedata.normalize("NFKD", (valor or "").strip().lower())
    return "".join(caractere for caractere in texto if not unicodedata.combining(caractere))


def dashboard(request):
    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    fim_mes = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    vendas_eventos = Venda.objects.filter(evento__isnull=False).exclude(status="cancelado")
    parcelas_eventos = Parcela.objects.filter(venda__evento__isnull=False).exclude(venda__status="cancelado")
    receitas_recebidas = parcelas_eventos.filter(status="pago", data_pagamento__range=(inicio_mes, fim_mes)).aggregate(
        total=Sum("valor")
    )["total"] or 0
    receitas_a_receber = parcelas_eventos.exclude(status="pago").aggregate(
        total=Sum("valor")
    )["total"] or 0
    despesas_pagas = Despesa.objects.filter(status="pago", data__range=(inicio_mes, fim_mes)).aggregate(total=Sum("valor"))[
        "total"
    ] or 0
    despesas_a_pagar = Despesa.objects.exclude(status="pago").filter(
        Q(vencimento__range=(inicio_mes, fim_mes)) | Q(data__range=(inicio_mes, fim_mes))
    ).aggregate(total=Sum("valor"))["total"] or 0
    saldo_atual = receitas_recebidas - despesas_pagas
    saldo_previsto = (receitas_recebidas + receitas_a_receber) - (despesas_pagas + despesas_a_pagar)
    tarefas_mes = Tarefa.objects.filter(data__range=(inicio_mes, fim_mes))
    totais = {
        "clientes": Cliente.objects.count(),
        "clientes_mes": Cliente.objects.filter(criado_em__year=hoje.year, criado_em__month=hoje.month).count(),
        "vendas": vendas_eventos.count(),
        "receita_total": vendas_eventos.aggregate(total=Sum("valor_total"))["total"] or 0,
        "receita_paga": parcelas_eventos.filter(status="pago").aggregate(total=Sum("valor"))["total"] or 0,
        "pendente": parcelas_eventos.exclude(status="pago").aggregate(total=Sum("valor"))["total"] or 0,
        "receitas_recebidas": receitas_recebidas,
        "receitas_a_receber": receitas_a_receber,
        "despesas_pagas": despesas_pagas,
        "despesas_a_pagar": despesas_a_pagar,
        "saldo_atual": saldo_atual,
        "saldo_previsto": saldo_previsto,
        "contratos_mes": vendas_eventos.filter(data_venda__range=(inicio_mes, fim_mes)).count(),
        "trabalhos_mes": Evento.objects.filter(data_festa__range=(inicio_mes, fim_mes)).count(),
        "tarefas_pendentes": Tarefa.objects.filter(status="pendente").count(),
        "tarefas_atrasadas": Tarefa.objects.filter(Q(status="atrasada") | Q(status="pendente", data__lt=hoje)).count(),
        "oportunidades": Oportunidade.objects.exclude(etapa__in=["fechado", "perdido"]).count(),
        "docs_pendentes": Documento.objects.filter(status="pendente").count(),
        "formularios_recebidos": Cliente.objects.filter(criado_em__date__gte=hoje - timedelta(days=30)).count(),
    }
    parcelas_alerta = parcelas_eventos.exclude(status="pago").filter(
        Q(vencimento__lt=hoje) | Q(lembrete_em__lte=hoje)
    )[:8]
    recompra_alerta = [cliente for cliente in Cliente.objects.all() if cliente.precisa_alerta_recompra][:8]
    ultimas_vendas = vendas_eventos.select_related("cliente").prefetch_related("parcelas")[:8]
    tarefas_semana = Tarefa.objects.select_related("cliente").filter(data__range=(hoje, hoje + timedelta(days=7)))[:5]
    ultimos_lancamentos = list(Despesa.objects.all()[:4]) + list(vendas_eventos.select_related("cliente")[:4])
    concluidas = tarefas_mes.filter(status="concluida").count()
    total_tarefas_mes = tarefas_mes.count()
    progresso_tarefas = round((concluidas / total_tarefas_mes) * 100) if total_tarefas_mes else 0
    formas_pagamento = []
    formas_labels = dict(Venda.FORMA_CHOICES)
    formas_qs = (
        parcelas_eventos.filter(status="pago", data_pagamento__range=(inicio_mes, fim_mes))
        .values("venda__forma_pagamento")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")
    )
    for item in formas_qs:
        formas_pagamento.append(
            {
                "nome": formas_labels.get(item["venda__forma_pagamento"], item["venda__forma_pagamento"]),
                "total": item["total"] or 0,
                "quantidade": item["quantidade"],
            }
        )
    meses = []
    for offset in range(5, -1, -1):
        mes_ref = add_months(inicio_mes, -offset)
        mes_fim = mes_ref.replace(day=monthrange(mes_ref.year, mes_ref.month)[1])
        recebido = parcelas_eventos.filter(status="pago", data_pagamento__range=(mes_ref, mes_fim)).aggregate(
            total=Sum("valor")
        )["total"] or 0
        pago = Despesa.objects.filter(status="pago", data__range=(mes_ref, mes_fim)).aggregate(total=Sum("valor"))[
            "total"
        ] or 0
        escala = max(recebido, pago, 1)
        meses.append(
            {
                "nome": mes_ref.strftime("%b"),
                "recebido": recebido,
                "pago": pago,
                "recebido_altura": max(int((recebido / escala) * 64), 6) if recebido else 0,
                "pago_altura": max(int((pago / escala) * 64), 6) if pago else 0,
            }
        )
    return render(
        request,
        "crm/dashboard.html",
        {
            "totais": totais,
            "parcelas_alerta": parcelas_alerta,
            "recompra_alerta": recompra_alerta,
            "ultimas_vendas": ultimas_vendas,
            "tarefas_semana": tarefas_semana,
            "progresso_tarefas": progresso_tarefas,
            "formas_pagamento": formas_pagamento,
            "meses": meses,
            "inicio_mes": inicio_mes,
            "fim_mes": fim_mes,
            "ultimos_lancamentos": ultimos_lancamentos,
        },
    )


def clientes(request):
    busca = request.GET.get("q", "").strip()
    queryset = Cliente.objects.annotate(total_vendas=Count("vendas"))
    if busca:
        queryset = queryset.filter(
            Q(nome__icontains=busca) | Q(telefone__icontains=busca) | Q(email__icontains=busca)
        )
    return render(request, "crm/clientes.html", {"clientes": queryset, "busca": busca})


def cliente_form(request, pk=None):
    cliente = get_object_or_404(Cliente, pk=pk) if pk else None
    initial = {}
    if not cliente:
        initial = {
            "nome": request.GET.get("nome", ""),
            "origem": request.GET.get("origem", ""),
            "tipo_evento": request.GET.get("tipo_evento", ""),
            "proxima_oportunidade": request.GET.get("proxima_oportunidade", ""),
            "observacoes": request.GET.get("observacoes", ""),
        }
    form = ClienteForm(request.POST or None, instance=cliente, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cliente salvo com sucesso.")
        return redirect("clientes")
    return render(request, "crm/form.html", {"form": form, "titulo": "Cliente", "voltar": "clientes"})


def cliente_excluir(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == "POST":
        cliente.delete()
        messages.success(request, "Cliente excluido.")
        return redirect("clientes")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": cliente, "voltar": "clientes"})


def financeiro(request):
    hoje = timezone.localdate()
    vendas = (
        Venda.objects.select_related("cliente", "evento")
        .prefetch_related("parcelas")
        .filter(evento__isnull=False)
        .exclude(status="cancelado")
        .order_by("cliente__nome", "-data_venda", "-id")
    )

    grupos = {
        "pagos": {
            "titulo": "Evento Pago",
            "descricao": "Eventos que ja estao marcados como pago.",
            "status_painel": "pago",
            "clientes": {},
        },
        "atrasados": {
            "titulo": "Clientes Em atraso",
            "descricao": "A vista vencido ou boleto parcelado com pagamento em atraso.",
            "status_painel": "vencido",
            "clientes": {},
        },
        "em_dia": {
            "titulo": "Clientes em dias",
            "descricao": "Boleto parcelado com pagamentos dentro do prazo.",
            "status_painel": "pendente",
            "clientes": {},
        },
    }

    for venda in vendas:
        parcelas = list(venda.parcelas.all())
        parcelas_vencidas = [
            parcela
            for parcela in parcelas
            if parcela.status in ["pendente", "atrasado"] and parcela.vencimento < hoje
        ]
        boleto_parcelado = venda.forma_pagamento == "boleto" and venda.condicao_pagamento == "parcelado"

        if venda.evento.pagamento_status == "pago":
            chave = "pagos"
        elif venda.evento.pagamento_status == "vencido":
            chave = "atrasados"
        elif boleto_parcelado:
            chave = "em_dia"
        else:
            continue

        grupos[chave]["clientes"].setdefault(
            venda.cliente_id,
            {
                "cliente": venda.cliente,
                "parcelas_vencidas": 0,
            },
        )
        grupos[chave]["clientes"][venda.cliente_id]["parcelas_vencidas"] += len(parcelas_vencidas)

    grupos_financeiros = []
    for grupo in grupos.values():
        clientes = sorted(grupo["clientes"].values(), key=lambda item: item["cliente"].nome.lower())
        grupos_financeiros.append({**grupo, "clientes": clientes, "total": len(clientes)})

    return render(request, "crm/financeiro.html", {"grupos_financeiros": grupos_financeiros})


def financeiro_cliente_painel(request, cliente_id):
    status = request.GET.get("status", "")
    hoje = timezone.localdate()
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    vendas = cliente.vendas.select_related("cliente", "evento").prefetch_related("parcelas")
    if status == "vencido":
        vendas = vendas.filter(parcelas__status__in=["pendente", "atrasado"], parcelas__vencimento__lt=hoje).distinct()
    elif status:
        vendas = vendas.filter(status=status)
    totais = vendas.exclude(status="cancelado").aggregate(total=Sum("valor_total"))["total"] or 0
    return render(
        request,
        "crm/financeiro_cliente_painel.html",
        {"cliente": cliente, "vendas": vendas, "status": status, "totais": totais},
    )


def venda_form(request, pk=None):
    venda = get_object_or_404(Venda, pk=pk) if pk else None
    form = VendaForm(request.POST or None, instance=venda)
    if request.method == "POST" and form.is_valid():
        venda = form.save()
        primeira_parcela = form.cleaned_data.get("primeira_parcela") or venda.data_venda
        gerar_parcelas(venda, primeira_parcela)
        messages.success(request, "Venda e parcelas salvas com sucesso.")
        return redirect("financeiro")
    return render(request, "crm/form.html", {"form": form, "titulo": "Venda financeira", "voltar": "financeiro"})


def venda_excluir(request, pk):
    venda = get_object_or_404(Venda, pk=pk)
    if request.method == "POST":
        venda.delete()
        messages.success(request, "Venda excluida.")
        return redirect("financeiro")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": venda, "voltar": "financeiro"})


def parcela_form(request, pk=None, venda_id=None):
    parcela = get_object_or_404(Parcela, pk=pk) if pk else None
    venda = get_object_or_404(Venda, pk=venda_id) if venda_id else parcela.venda
    form = ParcelaForm(request.POST or None, instance=parcela)
    if request.method == "POST" and form.is_valid():
        parcela = form.save(commit=False)
        parcela.venda = venda
        parcela.save()
        messages.success(request, "Parcela salva com sucesso.")
        return redirect("financeiro")
    return render(request, "crm/form.html", {"form": form, "titulo": f"Parcela - {venda}", "voltar": "financeiro"})


def parcela_excluir(request, pk):
    parcela = get_object_or_404(Parcela, pk=pk)
    if request.method == "POST":
        parcela.delete()
        messages.success(request, "Parcela excluida.")
        return redirect("financeiro")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": parcela, "voltar": "financeiro"})


def alertas(request):
    hoje = timezone.localdate()
    agora = timezone.localtime()
    parcelas = Parcela.objects.select_related("venda", "venda__cliente").exclude(status="pago").filter(
        Q(vencimento__lt=hoje) | Q(lembrete_em__lte=hoje)
    )
    compromissos_hoje = list(
        Tarefa.objects.select_related("cliente", "evento", "evento__cliente").filter(data=hoje).order_by("hora", "titulo")
    )
    for tarefa in compromissos_hoje:
        tarefa.alerta_estado = "sem-hora"
        tarefa.alerta_mensagem = "Compromisso de hoje sem horario definido."
        tarefa.pode_marcar_concluido = tarefa.status != "concluida"
        if tarefa.status == "concluida":
            tarefa.alerta_estado = "concluida"
            tarefa.alerta_mensagem = "Compromisso confirmado como realizado."
        elif tarefa.hora:
            inicio = timezone.make_aware(datetime.combine(hoje, tarefa.hora), timezone.get_current_timezone())
            minutos = int((inicio - agora).total_seconds() // 60)
            if minutos > 15:
                tarefa.alerta_estado = "lembrete"
                tarefa.alerta_mensagem = f"Lembrete: compromisso marcado para {tarefa.hora:%H:%M}."
            elif minutos >= 0:
                tarefa.alerta_estado = "alerta"
                tarefa.alerta_mensagem = "Alerta: faltam 15 minutos ou menos. Nao perca este compromisso."
            else:
                tarefa.alerta_estado = "passado"
                tarefa.alerta_mensagem = "Horario ja passou. Confirme se o compromisso foi realizado."
    clientes_recompra = [cliente for cliente in Cliente.objects.all() if cliente.precisa_alerta_recompra]
    clientes_evento_hoje = Cliente.objects.filter(data_evento=hoje)
    clientes_edicao = Cliente.objects.filter(data_evento=hoje - timedelta(days=1))
    clientes_copia_cartao = Cliente.objects.none()
    if hoje.weekday() == 0:
        clientes_copia_cartao = Cliente.objects.filter(data_evento__range=(hoje - timedelta(days=7), hoje - timedelta(days=1)))
    lembretes_anuais = LembreteAnual.objects.select_related("cliente", "evento").filter(
        data_alerta__lte=hoje,
        data_proximo_evento__gte=hoje,
    )
    return render(
        request,
        "crm/alertas.html",
        {
            "parcelas": parcelas,
            "compromissos_hoje": compromissos_hoje,
            "clientes_recompra": clientes_recompra,
            "clientes_evento_hoje": clientes_evento_hoje,
            "clientes_edicao": clientes_edicao,
            "clientes_copia_cartao": clientes_copia_cartao,
            "lembretes_anuais": lembretes_anuais,
            "hoje": hoje,
            "agora": agora,
        },
    )


def tarefa_marcar_concluida(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if request.method == "POST":
        tarefa.status = "concluida"
        tarefa.save(update_fields=["status"])
        messages.success(request, "Compromisso marcado como concluido.")
    return redirect(request.POST.get("next") or "alertas")


def despesas(request):
    status = request.GET.get("status", "")
    despesas_qs = Despesa.objects.all()
    if status:
        despesas_qs = despesas_qs.filter(status=status)
    return render(request, "crm/despesas.html", {"despesas": despesas_qs, "status": status})


def despesa_form(request, pk=None):
    despesa = get_object_or_404(Despesa, pk=pk) if pk else None
    form = DespesaForm(request.POST or None, instance=despesa)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Despesa salva com sucesso.")
        return redirect("despesas")
    return render(request, "crm/form.html", {"form": form, "titulo": "Despesa", "voltar": "despesas"})


def despesa_excluir(request, pk):
    despesa = get_object_or_404(Despesa, pk=pk)
    if request.method == "POST":
        despesa.delete()
        messages.success(request, "Despesa excluida.")
        return redirect("despesas")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": despesa, "voltar": "despesas"})


def pipeline(request):
    busca = request.GET.get("q", "").strip()
    hoje = timezone.localdate()
    inicio_relatorio = hoje - timedelta(days=30)
    etapas_visiveis = {"novo", "orcamento", "negociacao"}
    oportunidades = Oportunidade.objects.select_related("cliente")
    if busca:
        oportunidades = oportunidades.filter(Q(nome_lead__icontains=busca) | Q(cliente__nome__icontains=busca))

    oportunidades_30_dias = oportunidades.filter(criado_em__date__gte=inicio_relatorio)
    valor_em_vigor = Case(
        When(etapa__in=["negociacao", "fechado"], valor_negociado__isnull=False, then=F("valor_negociado")),
        default=F("valor_estimado"),
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    resumo_30_dias = {
        "total": oportunidades_30_dias.count(),
        "novos": oportunidades_30_dias.filter(etapa="novo").count(),
        "em_andamento": oportunidades_30_dias.filter(etapa__in=["orcamento", "negociacao"]).count(),
        "fechados": oportunidades_30_dias.filter(etapa="fechado").count(),
        "perdidos": oportunidades_30_dias.filter(etapa="perdido").count(),
        "valor_aberto": oportunidades_30_dias.filter(etapa__in=etapas_visiveis).aggregate(total=Sum(valor_em_vigor))["total"]
        or 0,
    }

    etapas = []
    for codigo, nome in Oportunidade.ETAPA_CHOICES:
        etapa_qs = oportunidades.filter(etapa=codigo)
        etapas.append(
            {
                "codigo": codigo,
                "nome": nome,
                "items": etapa_qs if codigo in etapas_visiveis else [],
                "total": etapa_qs.count(),
                "mostrar_cards": codigo in etapas_visiveis,
            }
        )
    return render(
        request,
        "crm/pipeline.html",
        {
            "etapas": etapas,
            "busca": busca,
            "resumo_30_dias": resumo_30_dias,
            "inicio_relatorio": inicio_relatorio,
            "fim_relatorio": hoje,
        },
    )


def oportunidade_form(request, pk=None):
    oportunidade = get_object_or_404(Oportunidade, pk=pk) if pk else None
    form = OportunidadeForm(request.POST or None, instance=oportunidade)
    if request.method == "POST" and form.is_valid():
        oportunidade = form.save()
        messages.success(request, "Oportunidade salva com sucesso.")
        if oportunidade.etapa == "fechado":
            evento = preparar_evento_da_oportunidade(oportunidade)
            messages.success(request, "Oportunidade fechada. Confira e complete o evento antes do cadastro do cliente.")
            return redirect(f"{reverse('evento_editar', args=[evento.pk])}?proximo=cliente&oportunidade={oportunidade.pk}")
        if oportunidade.etapa == "perdido":
            registrar_oportunidade_perdida(oportunidade)
            messages.success(request, "Oportunidade perdida arquivada para contato futuro.")
        return redirect("pipeline")
    return render(request, "crm/form.html", {"form": form, "titulo": "Oportunidade", "voltar": "pipeline"})


def oportunidade_reuniao(request, pk):
    oportunidade = get_object_or_404(Oportunidade, pk=pk)
    if request.method != "POST":
        return redirect("pipeline")

    form = ReuniaoLeadForm(request.POST)
    if form.is_valid():
        local = form.cleaned_data["local"].strip()
        Tarefa.objects.create(
            titulo=f"Reuniao - {oportunidade.nome_lead}",
            tipo="reuniao",
            data=form.cleaned_data["dia"],
            hora=form.cleaned_data["hora"],
            status="pendente",
            descricao=(
                f"Lead: {oportunidade.nome_lead}\n"
                f"Contato: {oportunidade.contato or '-'}\n"
                f"Local: {local}\n"
                f"Origem: {oportunidade.origem or oportunidade.titulo}"
            ),
        )
        oportunidade.proximo_contato = form.cleaned_data["dia"]
        oportunidade.save(update_fields=["proximo_contato", "atualizado_em"])
        messages.success(request, "Reuniao criada e adicionada na agenda.")
    else:
        messages.error(request, "Informe dia, hora e local para criar a reuniao.")
    return redirect("pipeline")


def preparar_evento_da_oportunidade(oportunidade):
    evento = (
        Evento.objects.filter(
            nome__iexact=oportunidade.nome_lead,
            data_festa=oportunidade.data_festa,
            tipo_evento=oportunidade.tipo_evento,
        )
        .order_by("-atualizado_em")
        .first()
    )
    if not evento:
        evento = Evento(nome=oportunidade.nome_lead)
    evento.nome = oportunidade.nome_lead
    evento.tipo_evento = oportunidade.tipo_evento
    evento.data_festa = oportunidade.data_festa
    evento.horario = oportunidade.horario
    evento.contato = oportunidade.contato
    if oportunidade.valor_em_vigor:
        evento.valor_cobrado = oportunidade.valor_em_vigor
    evento.observacoes = oportunidade.observacoes
    evento.save()

    oportunidade.etapa = "fechado"
    oportunidade.save(update_fields=["etapa", "atualizado_em"])
    return evento


def registrar_oportunidade_perdida(oportunidade):
    registro, _ = OportunidadePerdida.objects.update_or_create(
        oportunidade=oportunidade,
        defaults={
            "nome": oportunidade.nome_lead,
            "tipo_prospeccao": oportunidade.origem or oportunidade.titulo,
            "nome_indicacao": oportunidade.nome_indicacao,
            "tipo_evento": oportunidade.tipo_evento,
            "data_festa": oportunidade.data_festa,
            "horario": oportunidade.horario,
            "contato": oportunidade.contato,
            "observacoes": oportunidade.observacoes,
        },
    )
    return registro


def oportunidade_mover(request, pk, etapa):
    oportunidade = get_object_or_404(Oportunidade, pk=pk)
    if etapa in dict(Oportunidade.ETAPA_CHOICES):
        oportunidade.etapa = etapa
        if etapa == "fechado":
            evento = preparar_evento_da_oportunidade(oportunidade)
            messages.success(request, "Oportunidade fechada. Confira e complete o evento antes do cadastro do cliente.")
            return redirect(f"{reverse('evento_editar', args=[evento.pk])}?proximo=cliente&oportunidade={oportunidade.pk}")
        if etapa == "perdido":
            oportunidade.save(update_fields=["etapa", "atualizado_em"])
            registrar_oportunidade_perdida(oportunidade)
            messages.success(request, "Oportunidade perdida arquivada para contato futuro.")
            return redirect("pipeline")
        oportunidade.save(update_fields=["etapa", "atualizado_em"])
        if etapa in ["orcamento", "negociacao"]:
            return redirect("oportunidade_editar", pk=oportunidade.pk)
    return redirect("pipeline")


def oportunidade_excluir(request, pk):
    oportunidade = get_object_or_404(Oportunidade, pk=pk)
    if request.method == "POST":
        oportunidade.delete()
        messages.success(request, "Oportunidade excluida.")
        return redirect("pipeline")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": oportunidade, "voltar": "pipeline"})


def agenda(request):
    hoje = timezone.localdate()
    data_param = request.GET.get("data", "") or request.GET.get("semana", "")
    try:
        data_ref = date.fromisoformat(data_param)
    except ValueError:
        data_ref = hoje

    inicio_semana = data_ref - timedelta(days=(data_ref.weekday() + 1) % 7)
    fim_semana = inicio_semana + timedelta(days=6)
    inicio_mes = data_ref.replace(day=1)
    fim_mes = inicio_mes.replace(day=monthrange(inicio_mes.year, inicio_mes.month)[1])
    horas_grade = list(range(7, 24))
    tarefas = (
        Tarefa.objects.select_related("cliente", "evento", "evento__cliente", "evento__venda")
        .prefetch_related("evento__venda__parcelas")
        .filter(data__range=(inicio_semana, fim_semana))
        .order_by("data", "hora", "titulo")
    )

    tons_tipo = {
        "trabalho": "trabalho",
        "reuniao": "reuniao",
        "entrega": "entrega",
        "pagamento": "pagamento",
        "lembrete": "lembrete",
    }
    tarefas_por_dia = {inicio_semana + timedelta(days=offset): [] for offset in range(7)}
    for tarefa in tarefas:
        tarefas_por_dia.setdefault(tarefa.data, []).append(tarefa)

    dias_semana = []
    detalhes_tarefas = []
    for dia, tarefas_dia in tarefas_por_dia.items():
        itens_horario = []
        itens_sem_hora = []
        for tarefa in tarefas_dia:
            tom = tons_tipo.get(tarefa.tipo, "tarefa")
            detalhe_id = f"agendaDetalhe{tarefa.pk}"
            detalhes_tarefas.append(tarefa)
            item = {
                "tarefa": tarefa,
                "detalhe_id": detalhe_id,
                "tom": tom,
            }
            if tarefa.hora:
                minutos = (tarefa.hora.hour - horas_grade[0]) * 60 + tarefa.hora.minute
                topo = max(minutos, 0) * 30 / 60
                item["style"] = f"top: {topo:.0f}px; min-height: 30px;"
                itens_horario.append(item)
            else:
                itens_sem_hora.append(item)

        dias_semana.append(
            {
                "data": dia,
                "iso": dia.isoformat(),
                "numero": dia.day,
                "semana": ["Dom.", "Seg.", "Ter.", "Qua.", "Qui.", "Sex.", "Sab."][(dia.weekday() + 1) % 7],
                "hoje": dia == hoje,
                "selecionado": dia == data_ref,
                "itens_horario": itens_horario,
                "itens_sem_hora": itens_sem_hora,
                "total": len(tarefas_dia),
            }
        )

    mini_calendario = []
    for semana in Calendar(firstweekday=6).monthdatescalendar(inicio_mes.year, inicio_mes.month):
        semana_mini = []
        for dia in semana:
            semana_mini.append(
                {
                    "data": dia,
                    "iso": dia.isoformat(),
                    "numero": dia.day,
                    "no_mes": dia.month == inicio_mes.month,
                    "hoje": dia == hoje,
                    "selecionado": inicio_semana <= dia <= fim_semana,
                }
            )
        mini_calendario.append(semana_mini)

    tarefas_mes = Tarefa.objects.filter(data__range=(inicio_mes, fim_mes)).values("tipo").annotate(total=Count("id"))
    totais_mes = {item["tipo"]: item["total"] for item in tarefas_mes}

    contexto = {
        "tarefas": tarefas,
        "dias_semana": dias_semana,
        "mini_calendario": mini_calendario,
        "detalhes_tarefas": detalhes_tarefas,
        "horas_grade": horas_grade,
        "mes_titulo": f"{MESES_PT[inicio_mes.month - 1]} {inicio_mes.year}",
        "semana_titulo": f"{inicio_semana:%d/%m} - {fim_semana:%d/%m/%Y}",
        "semana_anterior": (inicio_semana - timedelta(days=7)).isoformat(),
        "semana_proxima": (inicio_semana + timedelta(days=7)).isoformat(),
        "hoje_iso": hoje.isoformat(),
        "totais_mes": totais_mes,
        "hoje": hoje,
    }
    return render(request, "crm/agenda.html", contexto)


def cobrancas(request):
    hoje = timezone.localdate()
    parcelas = Parcela.objects.select_related("venda", "venda__cliente").filter(
        venda__evento__isnull=False
    )
    grupos_base = [
        ("vencidos", "Vencidos", "Parcelas em atraso que precisam de cobranca.", "vencido"),
        ("pagos", "Pagos", "Parcelas recebidas e baixadas no financeiro.", "pago"),
        ("a_receber", "A Receber", "Parcelas pendentes dentro do prazo.", "pendente"),
    ]
    grupos_cobrancas = []
    for codigo, titulo, descricao, status in grupos_base:
        itens = [parcela for parcela in parcelas if parcela.status_financeiro == status]
        clientes = {}
        for parcela in itens:
            cliente = parcela.venda.cliente
            item = clientes.setdefault(
                cliente.pk,
                {"cliente": cliente, "parcelas": [], "total": Decimal("0.00"), "vencidas": 0},
            )
            item["parcelas"].append(parcela)
            item["total"] += parcela.valor
            if parcela.status_financeiro == "vencido":
                item["vencidas"] += 1
        grupos_cobrancas.append(
            {
                "codigo": codigo,
                "titulo": titulo,
                "descricao": descricao,
                "status": status,
                "clientes": sorted(clientes.values(), key=lambda item: item["cliente"].nome.lower()),
                "total": len(itens),
                "valor_total": sum((parcela.valor for parcela in itens), Decimal("0.00")),
            }
        )

    pagamentos = parcelas.exclude(status="pago")[:40]
    pagamentos_por_cliente = {}
    for parcela in pagamentos:
        cliente = parcela.venda.cliente
        item = pagamentos_por_cliente.setdefault(
            cliente.pk,
            {"cliente": cliente, "parcelas": [], "total": Decimal("0.00"), "vencidas": 0},
        )
        item["parcelas"].append(parcela)
        item["total"] += parcela.valor
        if parcela.status_financeiro == "vencido":
            item["vencidas"] += 1
    return render(
        request,
        "crm/cobrancas.html",
        {
            "grupos_cobrancas": grupos_cobrancas,
            "pagamentos_por_cliente": pagamentos_por_cliente.values(),
            "hoje": hoje,
        },
    )


def parcela_marcar_pago(request, pk):
    parcela = get_object_or_404(Parcela.objects.select_related("venda", "venda__evento"), pk=pk)
    if request.method == "POST":
        hoje = timezone.localdate()
        parcela.status = "pago"
        parcela.data_pagamento = hoje
        parcela.save(update_fields=["status", "data_pagamento"])

        venda = parcela.venda
        todas_pagas = not venda.parcelas.exclude(status="pago").exists()
        if todas_pagas:
            venda.status = "pago"
            venda.save(update_fields=["status", "atualizado_em"])
        elif venda.status == "pago":
            venda.status = "pendente"
            venda.save(update_fields=["status", "atualizado_em"])

        if hasattr(venda, "evento"):
            evento = venda.evento
            evento.pagamento_recebido = todas_pagas
            evento.save(update_fields=["pagamento_recebido", "atualizado_em"])

        messages.success(request, "Pagamento marcado como recebido.")
    return redirect(request.POST.get("next") or "cobrancas")


def eventos(request):
    busca = request.GET.get("q", "").strip()
    eventos_qs = Evento.objects.select_related("cliente", "venda").prefetch_related("venda__parcelas", "documentos")
    if busca:
        eventos_qs = eventos_qs.filter(Q(nome__icontains=busca) | Q(cliente__nome__icontains=busca) | Q(contato__icontains=busca))
    eventos_qs = eventos_qs.order_by("data_festa", "horario", "nome")

    grupos_por_mes = {}
    for evento in eventos_qs:
        if not evento.data_festa:
            continue
        chave = evento.data_festa.replace(day=1)
        grupos_por_mes.setdefault(
            chave,
            {
                "titulo": f"{MESES_PT[chave.month - 1]} {chave.year}",
                "descricao": "Eventos cadastrados para este mes.",
                "eventos": [],
            },
        )
        grupos_por_mes[chave]["eventos"].append(evento)

    grupos_eventos = []
    for chave in sorted(grupos_por_mes):
        grupo = grupos_por_mes[chave]
        grupos_eventos.append({**grupo, "total": len(grupo["eventos"])})

    return render(request, "crm/eventos.html", {"grupos_eventos": grupos_eventos, "busca": busca})


def relatorios(request):
    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    fim_mes = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    vendas_mes = Venda.objects.filter(evento__isnull=False).exclude(status="cancelado").filter(
        data_venda__range=(inicio_mes, fim_mes)
    )
    despesas_mes = Despesa.objects.filter(Q(data__range=(inicio_mes, fim_mes)) | Q(vencimento__range=(inicio_mes, fim_mes)))
    eventos_mes = Evento.objects.filter(
        Q(criado_em__date__range=(inicio_mes, fim_mes)) | Q(atualizado_em__date__range=(inicio_mes, fim_mes))
    ).distinct()
    contexto = {
        "inicio_mes": inicio_mes,
        "fim_mes": fim_mes,
        "receita_mes": vendas_mes.aggregate(total=Sum("valor_total"))["total"] or 0,
        "despesa_mes": despesas_mes.aggregate(total=Sum("valor"))["total"] or 0,
        "eventos_mes": eventos_mes.count(),
        "vendas_recentes": vendas_mes.select_related("cliente")[:8],
        "eventos_recentes": eventos_mes.select_related("cliente", "venda").order_by("-atualizado_em")[:8],
    }
    return render(request, "crm/relatorios.html", contexto)


def evento_form(request, pk=None):
    evento = get_object_or_404(Evento, pk=pk) if pk else None
    form = EventoForm(request.POST or None, instance=evento)
    if request.method == "POST" and form.is_valid():
        evento = form.save()
        messages.success(request, "Evento salvo com sucesso.")
        if request.GET.get("proximo") == "cliente" and evento.cliente_id:
            oportunidade_id = request.GET.get("oportunidade")
            if oportunidade_id:
                Oportunidade.objects.filter(pk=oportunidade_id).update(cliente=evento.cliente, atualizado_em=timezone.now())
            messages.success(request, "Cliente criado ou atualizado a partir do evento.")
            return redirect("cliente_editar", pk=evento.cliente_id)
        return redirect("eventos")
    return render(request, "crm/form.html", {"form": form, "titulo": "Evento", "voltar": "eventos"})


def evento_excluir(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    if request.method == "POST":
        evento.delete()
        messages.success(request, "Evento excluido.")
        return redirect("eventos")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": evento, "voltar": "eventos"})


def tarefa_form(request, pk=None):
    tarefa = get_object_or_404(Tarefa, pk=pk) if pk else None
    form = TarefaForm(request.POST or None, instance=tarefa)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tarefa salva com sucesso.")
        return redirect("agenda")
    return render(request, "crm/form.html", {"form": form, "titulo": "Tarefa ou trabalho", "voltar": "agenda"})


def tarefa_excluir(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if request.method == "POST":
        tarefa.delete()
        messages.success(request, "Tarefa excluida.")
        return redirect("agenda")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": tarefa, "voltar": "agenda"})


def documentos(request):
    docs = Documento.objects.select_related("cliente", "evento")
    return render(request, "crm/documentos.html", {"documentos": docs})


def clientes_exportar_planilha(request):
    conteudo = montar_xlsx_clientes(Cliente.objects.all())
    response = HttpResponse(
        conteudo,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="clientes.xlsx"'
    return response


def clientes_importar_planilha(request):
    if request.method != "POST":
        return redirect("documentos")

    arquivo = request.FILES.get("planilha")
    if not arquivo:
        messages.error(request, "Selecione uma planilha para importar.")
        return redirect("documentos")

    try:
        if arquivo.name.lower().endswith(".csv"):
            linhas = ler_linhas_csv(arquivo)
        elif arquivo.name.lower().endswith(".xlsx"):
            linhas = ler_linhas_xlsx(arquivo)
        else:
            messages.error(request, "Envie uma planilha .xlsx ou .csv.")
            return redirect("documentos")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, ET.ParseError, KeyError, IndexError) as exc:
        messages.error(request, f"Nao foi possivel ler a planilha: {exc}")
        return redirect("documentos")

    if not linhas:
        messages.warning(request, "A planilha esta vazia.")
        return redirect("documentos")

    cabecalho = [normalizar_cabecalho(coluna) for coluna in linhas[0]]
    campos_por_rotulo = {normalizar_cabecalho(rotulo): campo for campo, rotulo in CLIENTE_PLANILHA_CAMPOS}
    indices = {campos_por_rotulo[nome]: indice for indice, nome in enumerate(cabecalho) if nome in campos_por_rotulo}
    if "nome" not in indices:
        messages.error(request, "A planilha precisa ter uma coluna Nome.")
        return redirect("documentos")

    criados = 0
    atualizados = 0
    ignorados = 0
    for linha in linhas[1:]:
        dados = {}
        for campo, indice in indices.items():
            dados[campo] = linha[indice].strip() if indice < len(linha) and linha[indice] is not None else ""
        nome = dados.get("nome", "").strip()
        if not nome:
            ignorados += 1
            continue

        cliente = None
        email = dados.get("email", "").strip()
        if email:
            cliente = Cliente.objects.filter(email__iexact=email).first()
        if not cliente:
            cliente = Cliente.objects.filter(nome__iexact=nome).first()

        valores = {
            "nome": nome,
            "telefone": dados.get("telefone", ""),
            "email": email,
            "origem": dados.get("origem", ""),
            "tipo_evento": dados.get("tipo_evento", ""),
            "data_evento": ler_data_planilha(dados.get("data_evento", "")),
            "proxima_oportunidade": ler_data_planilha(dados.get("proxima_oportunidade", "")),
            "observacoes": dados.get("observacoes", ""),
        }
        if cliente:
            for campo, valor in valores.items():
                setattr(cliente, campo, valor)
            cliente.save()
            atualizados += 1
        else:
            Cliente.objects.create(**valores)
            criados += 1

    messages.success(
        request,
        f"Planilha importada: {criados} clientes criados, {atualizados} atualizados e {ignorados} linhas ignoradas.",
    )
    return redirect("documentos")


def documento_form(request, pk=None):
    documento = get_object_or_404(Documento, pk=pk) if pk else None
    initial = {}
    if not documento:
        evento_id = request.GET.get("evento")
        if evento_id:
            evento = get_object_or_404(Evento.objects.select_related("cliente"), pk=evento_id)
            initial = {
                "evento": evento,
                "cliente": evento.cliente,
                "titulo": f"Contrato - {evento.nome}",
                "contato_whatsapp": evento.contato or (evento.cliente.telefone if evento.cliente else ""),
                "contato_email": evento.cliente.email if evento.cliente else "",
                "data_limite": evento.data_festa,
            }
    form = DocumentoForm(request.POST or None, request.FILES or None, instance=documento, initial=initial)
    if request.method == "POST" and form.is_valid():
        documento = form.save(commit=False)
        if documento.evento and documento.evento.cliente_id:
            documento.cliente = documento.evento.cliente
        if documento.cliente:
            if not documento.contato_whatsapp:
                documento.contato_whatsapp = documento.cliente.telefone
            if not documento.contato_email:
                documento.contato_email = documento.cliente.email
        if documento.arquivo_assinado:
            documento.status = "assinado"
            if not documento.assinado_em:
                documento.assinado_em = timezone.localdate()
        documento.save()
        messages.success(request, "Documento salvo e anexado ao evento com sucesso.")
        return redirect("documentos")
    return render(request, "crm/form.html", {"form": form, "titulo": "Documento", "voltar": "documentos"})


def documento_excluir(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    if request.method == "POST":
        documento.delete()
        messages.success(request, "Documento excluido.")
        return redirect("documentos")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": documento, "voltar": "documentos"})


def documento_enviar(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    if request.method != "POST":
        return redirect("documentos")

    if documento.status == "assinado":
        messages.warning(request, "Documento ja esta marcado como assinado. Envio nao realizado.")
        return redirect("documentos")

    if documento.cliente:
        if not documento.contato_whatsapp:
            documento.contato_whatsapp = documento.cliente.telefone
        if not documento.contato_email:
            documento.contato_email = documento.cliente.email

    try:
        retorno = enviar_documento(documento)
    except EnvioDocumentoError as exc:
        documento.ultimo_envio_sucesso = False
        documento.ultimo_envio_retorno = str(exc)
        documento.ultimo_envio_em = timezone.now()
        documento.save(update_fields=["contato_whatsapp", "contato_email", "ultimo_envio_sucesso", "ultimo_envio_retorno", "ultimo_envio_em"])
        messages.error(request, f"Documento nao enviado: {exc}")
        return redirect("documentos")

    documento.status = "enviado"
    documento.enviado_em = timezone.localdate()
    documento.ultimo_envio_sucesso = True
    documento.ultimo_envio_retorno = retorno
    documento.ultimo_envio_em = timezone.now()
    documento.save(
        update_fields=[
            "contato_whatsapp",
            "contato_email",
            "status",
            "enviado_em",
            "ultimo_envio_sucesso",
            "ultimo_envio_retorno",
            "ultimo_envio_em",
        ]
    )
    messages.success(request, "Documento enviado com PDF e instrucoes para assinatura pelo gov.br.")
    return redirect("documentos")


def documento_whatsapp_manual(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    if documento.cliente:
        if not documento.contato_whatsapp:
            documento.contato_whatsapp = documento.cliente.telefone
        if not documento.contato_email:
            documento.contato_email = documento.cliente.email
        documento.save(update_fields=["contato_whatsapp", "contato_email"])
    try:
        url = link_whatsapp_manual(documento)
    except EnvioDocumentoError as exc:
        messages.error(request, str(exc))
        return redirect("documentos")
    return render(request, "crm/documento_whatsapp_pdf.html", {"documento": documento, "whatsapp_url": url})


def documento_pdf(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    response = HttpResponse(gerar_pdf_documento(documento), content_type="application/pdf")
    disposition = request.GET.get("download")
    modo = "attachment" if disposition == "1" else "inline"
    response["Content-Disposition"] = f'{modo}; filename="{nome_pdf_documento(documento)}"'
    return response
