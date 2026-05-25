from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ClienteForm, DespesaForm, DocumentoForm, OportunidadeForm, ParcelaForm, TarefaForm, VendaForm
from .models import Cliente, Despesa, Documento, Oportunidade, Parcela, Tarefa, Venda
from .pdf import gerar_pdf_documento, nome_pdf_documento
from .services import EnvioDocumentoError, enviar_documento, link_whatsapp_manual


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


def dashboard(request):
    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    fim_mes = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    receitas_recebidas = Parcela.objects.filter(status="pago", data_pagamento__range=(inicio_mes, fim_mes)).aggregate(
        total=Sum("valor")
    )["total"] or 0
    receitas_a_receber = Parcela.objects.exclude(status="pago").filter(vencimento__range=(inicio_mes, fim_mes)).aggregate(
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
        "vendas": Venda.objects.count(),
        "receita_total": Venda.objects.exclude(status="cancelado").aggregate(total=Sum("valor_total"))["total"] or 0,
        "receita_paga": Parcela.objects.filter(status="pago").aggregate(total=Sum("valor"))["total"] or 0,
        "pendente": Parcela.objects.exclude(status="pago").aggregate(total=Sum("valor"))["total"] or 0,
        "receitas_recebidas": receitas_recebidas,
        "receitas_a_receber": receitas_a_receber,
        "despesas_pagas": despesas_pagas,
        "despesas_a_pagar": despesas_a_pagar,
        "saldo_atual": saldo_atual,
        "saldo_previsto": saldo_previsto,
        "contratos_mes": Venda.objects.filter(data_venda__range=(inicio_mes, fim_mes)).count(),
        "trabalhos_mes": Tarefa.objects.filter(tipo="trabalho", data__range=(inicio_mes, fim_mes)).count(),
        "tarefas_pendentes": Tarefa.objects.filter(status="pendente").count(),
        "tarefas_atrasadas": Tarefa.objects.filter(Q(status="atrasada") | Q(status="pendente", data__lt=hoje)).count(),
        "oportunidades": Oportunidade.objects.exclude(etapa__in=["fechado", "perdido"]).count(),
        "docs_pendentes": Documento.objects.filter(status="pendente").count(),
        "formularios_recebidos": Cliente.objects.filter(criado_em__date__gte=hoje - timedelta(days=30)).count(),
    }
    parcelas_alerta = Parcela.objects.exclude(status="pago").filter(
        Q(vencimento__lt=hoje) | Q(lembrete_em__lte=hoje)
    )[:8]
    recompra_alerta = [cliente for cliente in Cliente.objects.all() if cliente.precisa_alerta_recompra][:8]
    ultimas_vendas = Venda.objects.select_related("cliente").prefetch_related("parcelas")[:8]
    tarefas_semana = Tarefa.objects.select_related("cliente").filter(data__range=(hoje, hoje + timedelta(days=7)))[:5]
    ultimos_lancamentos = list(Despesa.objects.all()[:4]) + list(Venda.objects.select_related("cliente")[:4])
    concluidas = tarefas_mes.filter(status="concluida").count()
    total_tarefas_mes = tarefas_mes.count()
    progresso_tarefas = round((concluidas / total_tarefas_mes) * 100) if total_tarefas_mes else 0
    meses = []
    for offset in range(5, -1, -1):
        mes_ref = add_months(inicio_mes, -offset)
        mes_fim = mes_ref.replace(day=monthrange(mes_ref.year, mes_ref.month)[1])
        recebido = Parcela.objects.filter(status="pago", data_pagamento__range=(mes_ref, mes_fim)).aggregate(
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
                "recebido_altura": max(int((recebido / escala) * 64), 6) if recebido else 6,
                "pago_altura": max(int((pago / escala) * 64), 6) if pago else 6,
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
    status = request.GET.get("status", "")
    hoje = timezone.localdate()
    clientes = Cliente.objects.filter(vendas__isnull=False).distinct().order_by("nome")
    if status == "vencido":
        clientes = clientes.filter(vendas__parcelas__status__in=["pendente", "atrasado"], vendas__parcelas__vencimento__lt=hoje)
    elif status:
        clientes = clientes.filter(vendas__status=status).distinct()
    clientes = clientes.annotate(
        total_vendas=Count("vendas", filter=Q(vendas__status=status)) if status and status != "vencido" else Count("vendas"),
        parcelas_vencidas=Count(
            "vendas__parcelas",
            filter=Q(vendas__parcelas__status__in=["pendente", "atrasado"], vendas__parcelas__vencimento__lt=hoje),
        ),
    )
    return render(request, "crm/financeiro.html", {"clientes": clientes, "status": status})


def financeiro_cliente_painel(request, cliente_id):
    status = request.GET.get("status", "")
    hoje = timezone.localdate()
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    vendas = cliente.vendas.select_related("cliente").prefetch_related("parcelas")
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
    parcelas = Parcela.objects.select_related("venda", "venda__cliente").exclude(status="pago").filter(
        Q(vencimento__lt=hoje) | Q(lembrete_em__lte=hoje)
    )
    clientes_recompra = [cliente for cliente in Cliente.objects.all() if cliente.precisa_alerta_recompra]
    return render(
        request,
        "crm/alertas.html",
        {"parcelas": parcelas, "clientes_recompra": clientes_recompra, "hoje": hoje},
    )


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
    etapas = []
    for codigo, nome in Oportunidade.ETAPA_CHOICES:
        etapas.append({"codigo": codigo, "nome": nome, "items": Oportunidade.objects.filter(etapa=codigo)})
    return render(request, "crm/pipeline.html", {"etapas": etapas})


def oportunidade_form(request, pk=None):
    oportunidade = get_object_or_404(Oportunidade, pk=pk) if pk else None
    form = OportunidadeForm(request.POST or None, instance=oportunidade)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Oportunidade salva com sucesso.")
        return redirect("pipeline")
    return render(request, "crm/form.html", {"form": form, "titulo": "Oportunidade", "voltar": "pipeline"})


def oportunidade_mover(request, pk, etapa):
    oportunidade = get_object_or_404(Oportunidade, pk=pk)
    if etapa in dict(Oportunidade.ETAPA_CHOICES):
        oportunidade.etapa = etapa
        if etapa == "fechado":
            cliente = oportunidade.cliente
            if not cliente:
                cliente, _ = Cliente.objects.get_or_create(
                    nome=oportunidade.nome_lead,
                    defaults={
                        "origem": oportunidade.origem,
                        "tipo_evento": oportunidade.tipo_evento or oportunidade.titulo,
                        "proxima_oportunidade": oportunidade.proximo_contato,
                        "observacoes": f"Criado automaticamente ao fechar a oportunidade: {oportunidade.titulo}.",
                    },
                )
                oportunidade.cliente = cliente
            oportunidade.save(update_fields=["etapa", "cliente", "atualizado_em"])
            messages.success(request, "Oportunidade fechada. Confira e complete o cadastro do cliente.")
            return redirect("cliente_editar", pk=cliente.pk)
        oportunidade.save(update_fields=["etapa", "atualizado_em"])
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
    tarefas = Tarefa.objects.select_related("cliente").filter(data__gte=hoje - timedelta(days=7))[:80]
    pagamentos = Parcela.objects.select_related("venda", "venda__cliente").exclude(status="pago").filter(
        vencimento__gte=hoje - timedelta(days=7)
    )[:40]
    pagamentos_por_cliente = {}
    for parcela in pagamentos:
        cliente = parcela.venda.cliente
        item = pagamentos_por_cliente.setdefault(
            cliente.pk,
            {"cliente": cliente, "parcelas": [], "total": Decimal("0.00")},
        )
        item["parcelas"].append(parcela)
        item["total"] += parcela.valor
    return render(
        request,
        "crm/agenda.html",
        {"tarefas": tarefas, "pagamentos_por_cliente": pagamentos_por_cliente.values(), "hoje": hoje},
    )


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
    docs = Documento.objects.select_related("cliente")
    return render(request, "crm/documentos.html", {"documentos": docs})


def documento_form(request, pk=None):
    documento = get_object_or_404(Documento, pk=pk) if pk else None
    form = DocumentoForm(request.POST or None, instance=documento)
    if request.method == "POST" and form.is_valid():
        documento = form.save(commit=False)
        if documento.cliente:
            if not documento.contato_whatsapp:
                documento.contato_whatsapp = documento.cliente.telefone
            if not documento.contato_email:
                documento.contato_email = documento.cliente.email
        documento.save()
        messages.success(request, "Documento salvo com sucesso.")
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
    messages.success(request, "Documento enviado de verdade pelo canal configurado.")
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
