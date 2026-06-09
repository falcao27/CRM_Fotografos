import csv
import io
import unicodedata
import zipfile
from calendar import Calendar, monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from html import escape
from urllib.parse import quote
from xml.etree import ElementTree as ET

from django.contrib import messages
from django.contrib.auth import authenticate, login as session_login, logout as session_logout
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.db.models import Case, Count, DecimalField, F, Q, Sum, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    AdminCompromissoForm,
    ClienteForm,
    calcular_proxima_oportunidade,
    ContratoAdminEmpresaForm,
    DespesaForm,
    DocumentoForm,
    EmpresaAdminForm,
    EventoForm,
    OportunidadeForm,
    ParcelaForm,
    ReuniaoLeadForm,
    TarefaForm,
    VendaForm,
)
from .models import (
    CONTRATO_FESTA_INFANTIL_TEMPLATE,
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
from .auth_jwt import JWT_COOKIE_NAME, JWT_MAX_AGE, gerar_token
from .pdf import gerar_pdf_documento, gerar_pdf_relatorio_despesas, gerar_pdf_relatorio_simples, nome_pdf_documento
from .services import EnvioDocumentoError, enviar_documento, link_whatsapp_manual, normalizar_whatsapp


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
    ("observacoes", "Observacoes"),
]


def formatar_moeda_whatsapp(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def link_whatsapp_parcelas(cliente, parcelas, tipo):
    numero = normalizar_whatsapp(cliente.telefone if cliente else "")
    if not numero:
        return ""

    parcelas = list(parcelas)
    total = sum((parcela.valor_em_aberto for parcela in parcelas), Decimal("0.00"))
    linhas = []
    for parcela in parcelas:
        linhas.append(
            "- Parcela "
            f"{parcela.numero}/{parcela.venda.quantidade_parcelas} "
            f"({parcela.venda.titulo}) no valor em aberto de {formatar_moeda_whatsapp(parcela.valor_em_aberto)}, "
            f"vencimento em {parcela.vencimento:%d/%m/%Y}."
        )

    nome = cliente.nome if cliente else ""
    if tipo == "vencido":
        mensagem = (
            f"Ola, {nome}.\n\n"
            "Consta pagamento em atraso referente a parcela ou parcelas abaixo:\n"
            f"{chr(10).join(linhas)}\n\n"
            f"Total em atraso: {formatar_moeda_whatsapp(total)}.\n\n"
            "Por favor, regularize o pagamento assim que possivel. Qualquer duvida, estou a disposicao."
        )
    else:
        mensagem = (
            f"Ola, {nome}.\n\n"
            "Passando para lembrar sobre o pagamento referente a parcela abaixo:\n"
            f"{chr(10).join(linhas)}\n\n"
            f"Valor total: {formatar_moeda_whatsapp(total)}.\n"
            "O vencimento e a data cadastrada no pagamento. Qualquer duvida, estou a disposicao."
        )
    return f"https://wa.me/{numero}?text={quote(mensagem)}"


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
            valor_recebido=valor if venda.status == "pago" else Decimal("0.00"),
            vencimento=vencimento,
            lembrete_em=vencimento - timedelta(days=3),
            status="pago" if venda.status == "pago" else "pendente",
            data_pagamento=venda.data_venda if venda.status == "pago" else None,
        )
        restante -= valor


def atualizar_status_venda(venda):
    if venda.status == "cancelado":
        return
    total_recebido = venda.valor_pago
    novo_status = "pago" if total_recebido >= venda.valor_total and venda.valor_total else "pendente"
    if venda.status != novo_status:
        venda.status = novo_status
        venda.save(update_fields=["status", "atualizado_em"])
    if hasattr(venda, "evento"):
        evento = venda.evento
        pagamento_recebido = novo_status == "pago"
        if evento.pagamento_recebido != pagamento_recebido:
            evento.pagamento_recebido = pagamento_recebido
            evento.save(update_fields=["pagamento_recebido", "atualizado_em"])


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
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
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


def data_financeira_despesa(despesa):
    return despesa.vencimento or despesa.data


def filtro_data_financeira_despesa(inicio, fim):
    return Q(vencimento__range=(inicio, fim)) | Q(vencimento__isnull=True, data__range=(inicio, fim))


def total_brl(valor):
    return f"{Decimal(valor or 0):.2f}".replace(".", ",")


def usuario_admin_master(user):
    perfil = getattr(user, "perfil_crm", None)
    return bool(user.is_superuser or (perfil and perfil.admin_master))


def empresa_atual(request):
    perfil = getattr(request.user, "perfil_crm", None)
    return perfil.empresa if perfil and not perfil.admin_master else None


def filtrar_empresa(qs, request):
    empresa = empresa_atual(request)
    if not empresa:
        return qs
    return qs.filter(empresa=empresa)


def filtrar_parcelas_empresa(qs, request):
    empresa = empresa_atual(request)
    if not empresa:
        return qs
    return qs.filter(venda__empresa=empresa)


def atribuir_empresa(obj, request):
    empresa = empresa_atual(request)
    if empresa and hasattr(obj, "empresa_id") and not obj.empresa_id:
        obj.empresa = empresa
    return obj


def exigir_admin_master(request):
    if usuario_admin_master(request.user):
        return None
    messages.error(request, "Acesso permitido apenas para o admin master.")
    return redirect("dashboard")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        tipo_login = request.POST.get("tipo_login", "cliente")
        user = authenticate(request, username=username, password=password)
        if user and user.is_active:
            perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
            admin_master = user.is_superuser or perfil.admin_master
            if tipo_login == "admin" and not admin_master:
                messages.error(request, "Este acesso nao pertence ao admin.")
                return render(request, "crm/login.html", {"next": request.GET.get("next", ""), "tipo_login": tipo_login})
            if tipo_login == "cliente" and admin_master:
                messages.error(request, "Use o acesso de admin para este usuario.")
                return render(request, "crm/login.html", {"next": request.GET.get("next", ""), "tipo_login": tipo_login})
            session_login(request, user)
            destino = "admin_master" if admin_master else "dashboard"
            response = redirect(request.POST.get("next") or request.GET.get("next") or destino)
            response.set_cookie(
                JWT_COOKIE_NAME,
                gerar_token(user),
                max_age=JWT_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=request.is_secure(),
            )
            return response
        messages.error(request, "Usuario ou senha invalidos.")

    tipo_login = request.GET.get("tipo", "cliente")
    if tipo_login not in ["cliente", "admin"]:
        tipo_login = "cliente"
    return render(request, "crm/login.html", {"next": request.GET.get("next", ""), "tipo_login": tipo_login})


def logout_view(request):
    session_logout(request)
    response = redirect("login")
    response.delete_cookie(JWT_COOKIE_NAME)
    return response


def cadastro_usuario(request):
    if request.method == "POST":
        empresa_nome = request.POST.get("empresa", "").strip()
        nome = request.POST.get("nome", "").strip()
        email = request.POST.get("email", "").strip()
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not all([empresa_nome, nome, username, password]):
            messages.error(request, "Preencha empresa, nome, usuario e senha.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Este usuario ja existe.")
        else:
            empresa = Empresa.objects.create(nome=empresa_nome, email=email)
            user = User.objects.create_user(username=username, password=password, email=email, first_name=nome, is_staff=True)
            PerfilUsuario.objects.create(user=user, empresa=empresa, papel="empresa_admin")
            messages.success(request, "Cadastro criado. Agora faca login.")
            return redirect("login")

    return render(request, "crm/cadastro.html")


def admin_master(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio

    try:
        dias_acesso = int(request.GET.get("dias", 7))
    except ValueError:
        dias_acesso = 7
    dias_acesso = min(max(dias_acesso, 1), 365)
    inicio_acessos = timezone.now() - timedelta(days=dias_acesso)

    ranking = (
        Empresa.objects.annotate(total_acessos=Count("acessos"))
        .order_by("-total_acessos", "nome")
    )
    contexto = {
        "ranking_empresas": ranking,
        "acessos": AcessoUsuario.objects.select_related("user", "empresa").filter(criado_em__gte=inicio_acessos)[:50],
        "dias_acesso": dias_acesso,
        "acesso_modal_aberto": request.GET.get("acessos") == "1",
    }
    return render(request, "crm/admin_master.html", contexto)


def admin_financeiro(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    contratos = ContratoAdminEmpresa.objects.select_related("empresa")
    contexto = {
        "contratos": contratos,
        "total_valor": contratos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00"),
        "total_pago": contratos.filter(status="pago").aggregate(total=Sum("valor"))["total"] or Decimal("0.00"),
        "total_pendente": contratos.exclude(status="pago").aggregate(total=Sum("valor"))["total"] or Decimal("0.00"),
    }
    return render(request, "crm/admin_financeiro.html", contexto)


def admin_empresa_form(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    form = EmpresaAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cliente/empresa cadastrado.")
        return redirect("admin_financeiro")
    return render(request, "crm/form.html", {"form": form, "titulo": "Cliente/empresa admin", "voltar": "admin_financeiro"})


def admin_contrato_form(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    form = ContratoAdminEmpresaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contrato administrativo cadastrado.")
        return redirect("admin_financeiro")
    return render(request, "crm/form.html", {"form": form, "titulo": "Contrato administrativo", "voltar": "admin_financeiro"})


def admin_relatorios(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    fim_mes = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    contratos_mes = ContratoAdminEmpresa.objects.filter(vencimento__range=(inicio_mes, fim_mes)).select_related("empresa")
    contexto = {
        "inicio_mes": inicio_mes,
        "fim_mes": fim_mes,
        "receita_mes": contratos_mes.filter(status="pago").aggregate(total=Sum("valor"))["total"] or Decimal("0.00"),
        "vendas_recentes": contratos_mes.order_by("-criado_em")[:8],
    }
    return render(request, "crm/admin_relatorios.html", contexto)


def admin_agenda(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
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
    compromissos = AdminCompromisso.objects.select_related("empresa").filter(data__range=(inicio_semana, fim_semana))
    tons_tipo = {"reuniao": "reuniao", "cobranca": "pagamento", "suporte": "entrega", "tarefa": "tarefa"}
    compromissos_mes = AdminCompromisso.objects.filter(data__range=(inicio_mes, fim_mes))
    tons_por_dia_mes = {}
    for compromisso in compromissos_mes:
        tom = tons_tipo.get(compromisso.tipo, "tarefa")
        tons = tons_por_dia_mes.setdefault(compromisso.data, [])
        if tom not in tons:
            tons.append(tom)

    compromissos_por_dia = {inicio_semana + timedelta(days=offset): [] for offset in range(7)}
    for compromisso in compromissos:
        compromissos_por_dia.setdefault(compromisso.data, []).append(compromisso)

    dias_semana = []
    for dia, compromissos_dia in compromissos_por_dia.items():
        itens_horario = []
        itens_sem_hora = []
        for compromisso in compromissos_dia:
            item = {"compromisso": compromisso, "tom": tons_tipo.get(compromisso.tipo, "tarefa")}
            if compromisso.hora:
                minutos = (compromisso.hora.hour - horas_grade[0]) * 60 + compromisso.hora.minute
                item["style"] = f"top: {max(minutos, 0) * 30 / 60:.0f}px; min-height: 30px;"
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
                "itens_horario": itens_horario,
                "itens_sem_hora": itens_sem_hora,
            }
        )

    calendario = Calendar(firstweekday=6)
    mini_calendario = []
    for semana in calendario.monthdatescalendar(data_ref.year, data_ref.month):
        mini_calendario.append(
            [
                {
                    "data": dia,
                    "iso": dia.isoformat(),
                    "numero": dia.day,
                    "no_mes": dia.month == data_ref.month,
                    "hoje": dia == hoje,
                    "selecionado": dia == data_ref,
                    "tons": tons_por_dia_mes.get(dia, []),
                }
                for dia in semana
            ]
        )
    contexto = {
        "hoje_iso": hoje.isoformat(),
        "semana_anterior": (inicio_semana - timedelta(days=7)).isoformat(),
        "semana_proxima": (inicio_semana + timedelta(days=7)).isoformat(),
        "semana_titulo": f"{inicio_semana:%d/%m} ate {fim_semana:%d/%m/%Y}",
        "mes_titulo": f"{MESES_PT[data_ref.month - 1]} {data_ref.year}",
        "mini_calendario": mini_calendario,
        "dias_semana": dias_semana,
        "horas_grade": horas_grade,
    }
    return render(request, "crm/admin_agenda.html", contexto)


def admin_compromisso_form(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    form = AdminCompromissoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Compromisso administrativo cadastrado.")
        return redirect("admin_agenda")
    return render(request, "crm/form.html", {"form": form, "titulo": "Compromisso admin", "voltar": "admin_agenda"})


def admin_clientes(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    empresas = Empresa.objects.prefetch_related("usuarios__user").annotate(total_acessos=Count("acessos"))
    return render(request, "crm/admin_clientes.html", {"empresas": empresas})


def admin_cobrancas(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    contratos = ContratoAdminEmpresa.objects.exclude(status="pago").select_related("empresa")
    return render(request, "crm/admin_cobrancas.html", {"contratos": contratos})


def admin_banco(request):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    return render(request, "crm/admin_banco.html")


def admin_acessar_cliente(request, empresa_id):
    bloqueio = exigir_admin_master(request)
    if bloqueio:
        return bloqueio
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    perfil_cliente = (
        PerfilUsuario.objects.select_related("user")
        .filter(empresa=empresa, papel__in=["empresa_admin", "empresa_usuario"], user__is_active=True)
        .first()
    )
    if not perfil_cliente:
        messages.error(request, "Esta empresa ainda nao tem usuario ativo.")
        return redirect("admin_clientes")
    session_login(request, perfil_cliente.user)
    response = redirect("dashboard")
    response.set_cookie(
        JWT_COOKIE_NAME,
        gerar_token(perfil_cliente.user),
        max_age=JWT_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure(),
    )
    return response


def dashboard(request):
    hoje = timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    fim_mes = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    filtro_receita = request.GET.get("receita", "mes")
    if filtro_receita not in ["mes", "todos"]:
        filtro_receita = "mes"
    vendas_eventos = filtrar_empresa(Venda.objects.filter(evento__isnull=False), request).exclude(status="cancelado")
    parcelas_eventos = filtrar_parcelas_empresa(
        Parcela.objects.filter(venda__evento__isnull=False).exclude(venda__status="cancelado"), request
    )
    eventos_com_adiantamento = filtrar_empresa(
        Evento.objects.filter(venda__isnull=False, adiantamento__gt=0, adiantamento_pago=True), request
    ).exclude(venda__status="cancelado")
    adiantamentos_mes = eventos_com_adiantamento.filter(venda__data_venda__range=(inicio_mes, fim_mes)).aggregate(
        total=Sum("adiantamento")
    )["total"] or 0
    receitas_recebidas = parcelas_eventos.filter(data_pagamento__range=(inicio_mes, fim_mes)).aggregate(
        total=Sum("valor_recebido")
    )["total"] or 0
    receitas_recebidas += adiantamentos_mes
    receitas_a_receber = (
        parcelas_eventos.exclude(status="pago")
        .filter(vencimento__range=(inicio_mes, fim_mes))
        .aggregate(total=Sum(F("valor") - F("valor_recebido"), output_field=DecimalField()))["total"]
        or 0
    )
    receitas_recebidas_todos = (parcelas_eventos.aggregate(total=Sum("valor_recebido"))["total"] or 0) + (
        eventos_com_adiantamento.aggregate(total=Sum("adiantamento"))["total"] or 0
    )
    receitas_a_receber_todos = parcelas_eventos.exclude(status="pago").aggregate(
        total=Sum(F("valor") - F("valor_recebido"), output_field=DecimalField())
    )["total"] or 0
    receita_total_eventos = vendas_eventos.aggregate(total=Sum("valor_total"))["total"] or 0
    if filtro_receita == "todos":
        receitas_recebidas = receitas_recebidas_todos
        receitas_a_receber = receitas_a_receber_todos
    despesas_pagas = (
        filtrar_empresa(Despesa.objects.filter(status="pago"), request)
        .filter(filtro_data_financeira_despesa(inicio_mes, fim_mes))
        .aggregate(total=Sum("valor"))["total"]
        or 0
    )
    despesas_a_pagar = (
        filtrar_empresa(Despesa.objects.exclude(status="pago"), request)
        .filter(filtro_data_financeira_despesa(inicio_mes, fim_mes))
        .aggregate(total=Sum("valor"))["total"]
        or 0
    )
    saldo_atual = receitas_recebidas - despesas_pagas
    saldo_previsto = (receitas_recebidas + receitas_a_receber) - (despesas_pagas + despesas_a_pagar)
    tarefas_mes = filtrar_empresa(Tarefa.objects.filter(data__range=(inicio_mes, fim_mes)), request)
    totais = {
        "clientes": filtrar_empresa(Cliente.objects, request).count(),
        "clientes_mes": filtrar_empresa(Cliente.objects.filter(criado_em__year=hoje.year, criado_em__month=hoje.month), request).count(),
        "vendas": vendas_eventos.count(),
        "receita_total": receita_total_eventos,
        "receita_paga": receitas_recebidas_todos,
        "pendente": receitas_a_receber_todos,
        "receitas_recebidas": receitas_recebidas,
        "receitas_a_receber": receitas_a_receber,
        "despesas_pagas": despesas_pagas,
        "despesas_a_pagar": despesas_a_pagar,
        "saldo_atual": saldo_atual,
        "saldo_previsto": saldo_previsto,
        "contratos_mes": vendas_eventos.filter(data_venda__range=(inicio_mes, fim_mes)).count(),
        "trabalhos_mes": filtrar_empresa(Evento.objects.filter(data_festa__range=(inicio_mes, fim_mes)), request).count(),
        "tarefas_pendentes": filtrar_empresa(Tarefa.objects.filter(status="pendente"), request).count(),
        "tarefas_atrasadas": filtrar_empresa(Tarefa.objects.filter(Q(status="atrasada") | Q(status="pendente", data__lt=hoje)), request).count(),
        "oportunidades": filtrar_empresa(Oportunidade.objects.exclude(etapa__in=["fechado", "perdido"]), request).count(),
        "docs_pendentes": filtrar_empresa(Documento.objects.filter(status="pendente"), request).count(),
        "formularios_recebidos": filtrar_empresa(Cliente.objects.filter(criado_em__date__gte=hoje - timedelta(days=30)), request).count(),
    }
    parcelas_alerta = parcelas_eventos.exclude(status="pago").filter(
        Q(vencimento__lt=hoje) | Q(lembrete_em__lte=hoje)
    )[:8]
    recompra_alerta = [cliente for cliente in filtrar_empresa(Cliente.objects.all(), request) if cliente.precisa_alerta_recompra][:8]
    ultimas_vendas = vendas_eventos.select_related("cliente").prefetch_related("parcelas")[:8]
    tarefas_semana = filtrar_empresa(Tarefa.objects.select_related("cliente").filter(data__range=(hoje, hoje + timedelta(days=7))), request)[:5]
    ultimos_lancamentos = list(filtrar_empresa(Despesa.objects.all(), request)[:4]) + list(vendas_eventos.select_related("cliente")[:4])
    concluidas = tarefas_mes.filter(status="concluida").count()
    total_tarefas_mes = tarefas_mes.count()
    progresso_tarefas = round((concluidas / total_tarefas_mes) * 100) if total_tarefas_mes else 0
    formas_pagamento = []
    formas_labels = dict(Venda.FORMA_CHOICES)
    formas_qs = (
        parcelas_eventos.filter(data_pagamento__range=(inicio_mes, fim_mes), valor_recebido__gt=0)
        .values("venda__forma_pagamento")
        .annotate(total=Sum("valor_recebido"), quantidade=Count("id"))
        .order_by("-total")
    )
    formas_totais = {}
    for item in formas_qs:
        forma = item["venda__forma_pagamento"]
        formas_totais[forma] = {
            "total": item["total"] or Decimal("0.00"),
            "quantidade": item["quantidade"],
        }
    adiantamentos_formas_qs = (
        eventos_com_adiantamento.filter(venda__data_venda__range=(inicio_mes, fim_mes))
        .values("venda__forma_pagamento")
        .annotate(total=Sum("adiantamento"), quantidade=Count("id"))
    )
    for item in adiantamentos_formas_qs:
        forma = item["venda__forma_pagamento"]
        total = formas_totais.setdefault(forma, {"total": Decimal("0.00"), "quantidade": 0})
        total["total"] += item["total"] or Decimal("0.00")
        total["quantidade"] += item["quantidade"]
    for forma, item in sorted(formas_totais.items(), key=lambda valor: valor[1]["total"], reverse=True):
        formas_pagamento.append(
            {"nome": formas_labels.get(forma, forma), "total": item["total"], "quantidade": item["quantidade"]}
        )
    meses = []
    for offset in range(5, -1, -1):
        mes_ref = add_months(inicio_mes, -offset)
        mes_fim = mes_ref.replace(day=monthrange(mes_ref.year, mes_ref.month)[1])
        recebido = parcelas_eventos.filter(data_pagamento__range=(mes_ref, mes_fim)).aggregate(
            total=Sum("valor_recebido")
        )["total"] or 0
        recebido += eventos_com_adiantamento.filter(venda__data_venda__range=(mes_ref, mes_fim)).aggregate(
            total=Sum("adiantamento")
        )["total"] or 0
        pago = (
            filtrar_empresa(Despesa.objects.filter(status="pago"), request)
            .filter(filtro_data_financeira_despesa(mes_ref, mes_fim))
            .aggregate(total=Sum("valor"))["total"]
            or 0
        )
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
            "filtro_receita": filtro_receita,
            "ultimos_lancamentos": ultimos_lancamentos,
        },
    )


def clientes(request):
    busca = request.GET.get("q", "").strip()
    queryset = filtrar_empresa(Cliente.objects, request).annotate(
        total_vendas=Count("vendas", filter=Q(vendas__evento__isnull=False))
    )
    if busca:
        queryset = queryset.filter(
            Q(nome__icontains=busca) | Q(telefone__icontains=busca) | Q(email__icontains=busca)
        )
    return render(request, "crm/clientes.html", {"clientes": queryset, "busca": busca})


def cliente_form(request, pk=None):
    cliente = get_object_or_404(filtrar_empresa(Cliente.objects, request), pk=pk) if pk else None
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
        cliente = form.save(commit=False)
        atribuir_empresa(cliente, request)
        cliente.save()
        messages.success(request, "Cliente salvo com sucesso.")
        return redirect("clientes")
    return render(request, "crm/form.html", {"form": form, "titulo": "Cliente", "voltar": "clientes"})


def cliente_excluir(request, pk):
    cliente = get_object_or_404(filtrar_empresa(Cliente.objects, request), pk=pk)
    if request.method == "POST":
        cliente.delete()
        messages.success(request, "Cliente excluido.")
        return redirect("clientes")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": cliente, "voltar": "clientes"})


def financeiro(request):
    hoje = timezone.localdate()
    vendas = (
        filtrar_empresa(Venda.objects.select_related("cliente", "evento"), request)
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
            "descricao": "Eventos com parcela vencida ou pagamento parcial em atraso.",
            "status_painel": "vencido",
            "clientes": {},
        },
        "em_dia": {
            "titulo": "Clientes em dias",
            "descricao": "Eventos com parcelas abertas dentro do prazo.",
            "status_painel": "pendente",
            "clientes": {},
        },
    }

    for venda in vendas:
        parcelas = list(venda.parcelas.all())
        parcelas_vencidas = [
            parcela
            for parcela in parcelas
            if parcela.status in ["pendente", "parcial", "atrasado"] and parcela.vencimento < hoje
        ]
        parcelas_abertas = [parcela for parcela in parcelas if parcela.status != "pago"]

        if venda.evento.pagamento_status == "pago":
            chave = "pagos"
        elif venda.evento.pagamento_status == "vencido":
            chave = "atrasados"
        elif parcelas_abertas or venda.status == "pendente":
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
    cliente = get_object_or_404(filtrar_empresa(Cliente.objects, request), pk=cliente_id)
    vendas = cliente.vendas.select_related("cliente", "evento").prefetch_related("parcelas")
    if status == "vencido":
        vendas = vendas.filter(parcelas__status__in=["pendente", "parcial", "atrasado"], parcelas__vencimento__lt=hoje).distinct()
    elif status:
        vendas = vendas.filter(status=status)
    totais = vendas.exclude(status="cancelado").aggregate(total=Sum("valor_total"))["total"] or 0
    return render(
        request,
        "crm/financeiro_cliente_painel.html",
        {"cliente": cliente, "vendas": vendas, "status": status, "totais": totais},
    )


def venda_form(request, pk=None):
    venda = get_object_or_404(filtrar_empresa(Venda.objects, request), pk=pk) if pk else None
    form = VendaForm(request.POST or None, instance=venda)
    empresa = empresa_atual(request)
    if empresa:
        form.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa)
    if request.method == "POST" and form.is_valid():
        venda = form.save(commit=False)
        atribuir_empresa(venda, request)
        if venda.cliente_id and not venda.empresa_id:
            venda.empresa = venda.cliente.empresa
        venda.save()
        form.save_m2m()
        primeira_parcela = form.cleaned_data.get("primeira_parcela") or venda.data_venda
        gerar_parcelas(venda, primeira_parcela)
        messages.success(request, "Venda e parcelas salvas com sucesso.")
        return redirect("financeiro")
    return render(request, "crm/form.html", {"form": form, "titulo": "Venda financeira", "voltar": "financeiro"})


def venda_excluir(request, pk):
    venda = get_object_or_404(filtrar_empresa(Venda.objects, request), pk=pk)
    if request.method == "POST":
        venda.delete()
        messages.success(request, "Venda excluida.")
        return redirect("financeiro")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": venda, "voltar": "financeiro"})


def parcela_form(request, pk=None, venda_id=None):
    parcela = get_object_or_404(filtrar_parcelas_empresa(Parcela.objects, request), pk=pk) if pk else None
    venda = get_object_or_404(filtrar_empresa(Venda.objects, request), pk=venda_id) if venda_id else parcela.venda
    form = ParcelaForm(request.POST or None, instance=parcela)
    if request.method == "POST" and form.is_valid():
        parcela = form.save(commit=False)
        parcela.venda = venda
        parcela.save()
        atualizar_status_venda(venda)
        messages.success(request, "Parcela salva com sucesso.")
        return redirect("financeiro")
    return render(request, "crm/form.html", {"form": form, "titulo": f"Parcela - {venda}", "voltar": "financeiro"})


def parcela_excluir(request, pk):
    parcela = get_object_or_404(filtrar_parcelas_empresa(Parcela.objects, request), pk=pk)
    if request.method == "POST":
        parcela.delete()
        messages.success(request, "Parcela excluida.")
        return redirect("financeiro")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": parcela, "voltar": "financeiro"})


def alertas(request):
    hoje = timezone.localdate()
    agora = timezone.localtime()
    parcelas = filtrar_parcelas_empresa(Parcela.objects.select_related("venda", "venda__cliente"), request).exclude(status="pago").filter(
        Q(vencimento__lt=hoje) | Q(lembrete_em__lte=hoje)
    )
    for parcela in parcelas:
        parcela.whatsapp_url = link_whatsapp_parcelas(
            parcela.venda.cliente,
            [parcela],
            "vencido" if parcela.status_financeiro == "vencido" else "lembrete",
        )
    compromissos_hoje = list(
        filtrar_empresa(Tarefa.objects.select_related("cliente", "evento", "evento__cliente"), request).filter(data=hoje).order_by("hora", "titulo")
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
    clientes_recompra = [cliente for cliente in filtrar_empresa(Cliente.objects.all(), request) if cliente.precisa_alerta_recompra]
    clientes_evento_hoje = filtrar_empresa(Cliente.objects.filter(data_evento=hoje), request)
    clientes_edicao = filtrar_empresa(Cliente.objects.filter(data_evento=hoje - timedelta(days=1)), request)
    clientes_copia_cartao = Cliente.objects.none()
    if hoje.weekday() == 0:
        clientes_copia_cartao = filtrar_empresa(Cliente.objects.filter(data_evento__range=(hoje - timedelta(days=7), hoje - timedelta(days=1))), request)
    lembretes_anuais = filtrar_empresa(LembreteAnual.objects.select_related("cliente", "evento"), request).filter(
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
    tarefa = get_object_or_404(filtrar_empresa(Tarefa.objects, request), pk=pk)
    if request.method == "POST":
        tarefa.status = "concluida"
        tarefa.save(update_fields=["status"])
        messages.success(request, "Compromisso marcado como concluido.")
    return redirect(request.POST.get("next") or "alertas")


def despesas(request):
    status = request.GET.get("status", "")
    despesas_qs = filtrar_empresa(Despesa.objects.all(), request).order_by("vencimento", "data", "descricao")
    if status:
        despesas_qs = despesas_qs.filter(status=status)

    grupos_por_mes = {}
    for despesa in despesas_qs:
        chave = data_financeira_despesa(despesa).replace(day=1)
        grupos_por_mes.setdefault(
            chave,
            {
                "chave": chave,
                "titulo": f"{MESES_PT[chave.month - 1]} {chave.year}",
                "descricao": "Despesas por vencimento ou pagamento.",
                "despesas": [],
                "total_valor": Decimal("0.00"),
                "pagas": 0,
                "pendentes": 0,
            },
        )
        grupo = grupos_por_mes[chave]
        grupo["despesas"].append(despesa)
        grupo["total_valor"] += despesa.valor
        if despesa.status == "pago":
            grupo["pagas"] += 1
        else:
            grupo["pendentes"] += 1

    grupos_despesas = []
    for chave in sorted(grupos_por_mes):
        grupo = grupos_por_mes[chave]
        grupos_despesas.append({**grupo, "total": len(grupo["despesas"])})

    return render(
        request,
        "crm/despesas.html",
        {"grupos_despesas": grupos_despesas, "status": status},
    )


def despesas_relatorio_pdf(request, ano, mes):
    status = request.GET.get("status", "")
    inicio = date(ano, mes, 1)
    fim = inicio.replace(day=monthrange(ano, mes)[1])
    despesas_qs = (
        filtrar_empresa(Despesa.objects.filter(filtro_data_financeira_despesa(inicio, fim)), request)
        .order_by("vencimento", "data", "descricao")
    )
    if status:
        despesas_qs = despesas_qs.filter(status=status)
    despesas_lista = list(despesas_qs)
    total = sum((despesa.valor for despesa in despesas_lista), Decimal("0.00"))
    titulo = f"Relatorio de despesas - {MESES_PT[mes - 1]} {ano}"
    if status:
        titulo += f" - {dict(Despesa.STATUS_CHOICES).get(status, status)}"
    response = HttpResponse(
        gerar_pdf_relatorio_despesas(titulo, despesas_lista, total),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = f'inline; filename="despesas_{ano}_{mes:02d}.pdf"'
    return response


def despesa_form(request, pk=None):
    despesa = get_object_or_404(filtrar_empresa(Despesa.objects, request), pk=pk) if pk else None
    form = DespesaForm(request.POST or None, instance=despesa)
    if request.method == "POST" and form.is_valid():
        despesa = form.save(commit=False)
        atribuir_empresa(despesa, request)
        despesa.save()
        messages.success(request, "Despesa salva com sucesso.")
        return redirect("despesas")
    return render(request, "crm/form.html", {"form": form, "titulo": "Despesa", "voltar": "despesas"})


def despesa_excluir(request, pk):
    despesa = get_object_or_404(filtrar_empresa(Despesa.objects, request), pk=pk)
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
    oportunidades = filtrar_empresa(Oportunidade.objects.select_related("cliente"), request)
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
    oportunidade = get_object_or_404(filtrar_empresa(Oportunidade.objects, request), pk=pk) if pk else None
    form = OportunidadeForm(request.POST or None, instance=oportunidade)
    empresa = empresa_atual(request)
    if empresa:
        form.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa)
    if request.method == "POST" and form.is_valid():
        oportunidade = form.save(commit=False)
        atribuir_empresa(oportunidade, request)
        oportunidade.save()
        form.save_m2m()
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
    oportunidade = get_object_or_404(filtrar_empresa(Oportunidade.objects, request), pk=pk)
    if request.method != "POST":
        return redirect("pipeline")

    form = ReuniaoLeadForm(request.POST)
    if form.is_valid():
        local = form.cleaned_data["local"].strip()
        Tarefa.objects.create(
            empresa=oportunidade.empresa,
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
            empresa=oportunidade.empresa,
            nome__iexact=oportunidade.nome_lead,
            data_festa=oportunidade.data_festa,
            tipo_evento=oportunidade.tipo_evento,
        )
        .order_by("-atualizado_em")
        .first()
    )
    if not evento:
        evento = Evento(nome=oportunidade.nome_lead, empresa=oportunidade.empresa)
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
            "empresa": oportunidade.empresa,
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
    oportunidade = get_object_or_404(filtrar_empresa(Oportunidade.objects, request), pk=pk)
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
    oportunidade = get_object_or_404(filtrar_empresa(Oportunidade.objects, request), pk=pk)
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
        filtrar_empresa(Tarefa.objects.select_related("cliente", "evento", "evento__cliente", "evento__venda"), request)
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
    tarefas_mes_lista = filtrar_empresa(Tarefa.objects.filter(data__range=(inicio_mes, fim_mes)), request).order_by("data", "tipo")
    tons_por_dia_mes = {}
    for tarefa in tarefas_mes_lista:
        tom = tons_tipo.get(tarefa.tipo, "tarefa")
        tons = tons_por_dia_mes.setdefault(tarefa.data, [])
        if tom not in tons:
            tons.append(tom)

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
                    "tons": tons_por_dia_mes.get(dia, []),
                }
            )
        mini_calendario.append(semana_mini)

    tarefas_mes = tarefas_mes_lista.values("tipo").annotate(total=Count("id"))
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
    parcelas = filtrar_parcelas_empresa(Parcela.objects.select_related("venda", "venda__cliente"), request).filter(
        venda__evento__isnull=False
    )
    grupos_base = [
        ("vencidos", "Vencidos", "", "vencido"),
        ("parciais", "Parciais", "", "parcial"),
        ("pagos", "Pagos", "", "pago"),
        ("a_receber", "A Receber", "", "pendente"),
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
            item["total"] += parcela.valor_recebido_efetivo if status == "pago" else parcela.valor_em_aberto
            if parcela.status_financeiro == "vencido":
                item["vencidas"] += 1
        for item in clientes.values():
            if status == "vencido":
                item["whatsapp_url"] = link_whatsapp_parcelas(item["cliente"], item["parcelas"], "vencido")
            elif status in ["pendente", "parcial"]:
                item["whatsapp_url"] = link_whatsapp_parcelas(item["cliente"], item["parcelas"], "lembrete")
            else:
                item["whatsapp_url"] = ""
        grupos_cobrancas.append(
            {
                "codigo": codigo,
                "titulo": titulo,
                "descricao": descricao,
                "status": status,
                "clientes": sorted(clientes.values(), key=lambda item: item["cliente"].nome.lower()),
                "total": len(itens),
                "valor_total": sum(
                    (
                        parcela.valor_recebido_efetivo if status == "pago" else parcela.valor_em_aberto
                        for parcela in itens
                    ),
                    Decimal("0.00"),
                ),
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
        item["total"] += parcela.valor_em_aberto
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
    parcela = get_object_or_404(filtrar_parcelas_empresa(Parcela.objects.select_related("venda", "venda__evento"), request), pk=pk)
    if request.method == "POST":
        hoje = timezone.localdate()
        valor_baixa = decimal_brasileiro(request.POST.get("valor_recebido"))
        if valor_baixa is None:
            valor_baixa = parcela.valor_em_aberto or parcela.valor
        parcela.valor_recebido = (parcela.valor_recebido or Decimal("0.00")) + valor_baixa
        parcela.data_pagamento = hoje
        parcela.status = "pago" if parcela.valor_recebido >= parcela.valor else "parcial"
        parcela.save(update_fields=["valor_recebido", "status", "data_pagamento"])

        venda = parcela.venda
        atualizar_status_venda(venda)

        messages.success(request, "Recebimento registrado no financeiro.")
    return redirect(request.POST.get("next") or "cobrancas")


def decimal_brasileiro(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    elif valor.count(".") > 1:
        partes = valor.split(".")
        valor = "".join(partes[:-1]) + "." + partes[-1]
    try:
        return Decimal(valor).quantize(Decimal("0.01"))
    except Exception:
        return None


def parcelas_do_request(request, form):
    numeros = request.POST.getlist("parcela_numero")
    valores = request.POST.getlist("parcela_valor")
    vencimentos = request.POST.getlist("parcela_vencimento")
    parcelas = []
    houve_erro = False

    for indice, numero_texto in enumerate(numeros):
        numero_texto = (numero_texto or "").strip()
        valor_texto = valores[indice] if indice < len(valores) else ""
        vencimento_texto = vencimentos[indice] if indice < len(vencimentos) else ""
        if not numero_texto and not valor_texto and not vencimento_texto:
            continue

        try:
            numero = int(numero_texto)
        except ValueError:
            numero = 0
        valor = decimal_brasileiro(valor_texto)
        vencimento = None
        if vencimento_texto:
            try:
                vencimento = date.fromisoformat(vencimento_texto)
            except ValueError:
                vencimento = None

        if numero < 1:
            form.add_error(None, "Informe o numero de cada parcela.")
            houve_erro = True
        if valor is None:
            form.add_error(None, "Informe o valor de cada parcela.")
            houve_erro = True
        if vencimento is None:
            form.add_error(None, "Informe a data de vencimento de cada parcela.")
            houve_erro = True

        parcelas.append({"numero": numero, "valor": valor or Decimal("0.00"), "vencimento": vencimento})

    if not parcelas:
        form.add_error(None, "Informe pelo menos uma parcela com numero, valor e vencimento.")
        houve_erro = True

    numeros_repetidos = len({parcela["numero"] for parcela in parcelas}) != len(parcelas)
    if numeros_repetidos:
        form.add_error(None, "Os numeros das parcelas nao podem se repetir.")
        houve_erro = True
    total_parcelas = sum((parcela["valor"] for parcela in parcelas), Decimal("0.00"))
    valor_total = form.cleaned_data.get("valor_cobrado") or Decimal("0.00")
    adiantamento = form.cleaned_data.get("adiantamento") or Decimal("0.00")
    valor_restante = max(valor_total - adiantamento, Decimal("0.00"))
    if total_parcelas != valor_restante:
        form.add_error(None, "A soma das parcelas precisa ser igual ao valor restante.")
        houve_erro = True

    return [] if houve_erro else sorted(parcelas, key=lambda item: item["numero"])


def parcelas_para_formulario(evento=None, request=None):
    if request and request.method == "POST":
        numeros = request.POST.getlist("parcela_numero")
        valores = request.POST.getlist("parcela_valor")
        vencimentos = request.POST.getlist("parcela_vencimento")
        return [
            {
                "numero": numeros[indice] if indice < len(numeros) else indice + 1,
                "valor": valores[indice] if indice < len(valores) else "",
                "vencimento": vencimentos[indice] if indice < len(vencimentos) else "",
            }
            for indice in range(max(len(numeros), len(valores), len(vencimentos), 1))
        ]
    if evento and evento.venda_id:
        return [
            {
                "numero": parcela.numero,
                "valor": f"{parcela.valor:.2f}".replace(".", ","),
                "vencimento": parcela.vencimento.isoformat(),
            }
            for parcela in evento.venda.parcelas.all()
        ]
    return [{"numero": 1, "valor": "", "vencimento": ""}]


def aplicar_parcelas_evento(evento, parcelas):
    if not evento.venda_id or not parcelas:
        return
    venda = evento.venda
    hoje = timezone.localdate()
    parcelas_mantidas = []
    for item in parcelas:
        parcela = venda.parcelas.filter(numero=item["numero"]).first() or Parcela(venda=venda, numero=item["numero"])
        parcela.valor = item["valor"]
        parcela.vencimento = item["vencimento"]
        parcela.lembrete_em = item["vencimento"]
        if evento.pagamento_recebido:
            parcela.valor_recebido = parcela.valor
            parcela.status = "pago"
            parcela.data_pagamento = hoje
        elif not parcela.valor_recebido:
            parcela.status = "pendente"
            parcela.data_pagamento = None
        parcela.observacoes = "Informada no formulario de contrato do evento."
        parcela.save()
        parcelas_mantidas.append(parcela.pk)
    venda.parcelas.exclude(pk__in=parcelas_mantidas).delete()
    venda.quantidade_parcelas = len(parcelas)
    venda.condicao_pagamento = "parcelado" if len(parcelas) > 1 else "avista"
    venda.valor_total = evento.valor_cobrado
    venda.status = "pago" if venda.valor_pago >= venda.valor_total and venda.valor_total else "pendente"
    venda.save(update_fields=["quantidade_parcelas", "condicao_pagamento", "valor_total", "status", "atualizado_em"])


def eventos(request):
    busca = request.GET.get("q", "").strip()
    eventos_qs = filtrar_empresa(Evento.objects.select_related("cliente", "venda"), request).prefetch_related("venda__parcelas", "documentos")
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
    vendas_mes = filtrar_empresa(Venda.objects.filter(evento__isnull=False), request).exclude(status="cancelado").filter(
        data_venda__range=(inicio_mes, fim_mes)
    )
    parcelas_recebidas_mes = filtrar_parcelas_empresa(Parcela.objects.filter(
        venda__evento__isnull=False,
        data_pagamento__range=(inicio_mes, fim_mes),
    ), request)
    adiantamentos_recebidos_mes = filtrar_empresa(Evento.objects.filter(
        venda__isnull=False,
        adiantamento__gt=0,
        adiantamento_pago=True,
        venda__data_venda__range=(inicio_mes, fim_mes),
    ), request).exclude(venda__status="cancelado")
    despesas_mes = filtrar_empresa(Despesa.objects.filter(filtro_data_financeira_despesa(inicio_mes, fim_mes)), request)
    eventos_mes = filtrar_empresa(Evento.objects.filter(
        Q(criado_em__date__range=(inicio_mes, fim_mes)) | Q(atualizado_em__date__range=(inicio_mes, fim_mes))
    ), request).distinct()
    contexto = {
        "inicio_mes": inicio_mes,
        "fim_mes": fim_mes,
        "receita_mes": (parcelas_recebidas_mes.aggregate(total=Sum("valor_recebido"))["total"] or 0)
        + (adiantamentos_recebidos_mes.aggregate(total=Sum("adiantamento"))["total"] or 0),
        "despesa_mes": despesas_mes.aggregate(total=Sum("valor"))["total"] or 0,
        "eventos_mes": eventos_mes.count(),
        "vendas_recentes": vendas_mes.select_related("cliente")[:8],
        "eventos_recentes": eventos_mes.select_related("cliente", "venda").order_by("-atualizado_em")[:8],
    }
    return render(request, "crm/relatorios.html", contexto)


def relatorios_pdf(request, tipo, ano, mes):
    tipos = {
        "receita": "Receita do Mes",
        "despesas": "Despesas do Mes",
        "eventos": "Eventos no Mes",
        "vendas": "Vendas recentes",
        "eventos-recentes": "Eventos recentes",
    }
    if tipo not in tipos or mes < 1 or mes > 12:
        return redirect("relatorios")

    inicio = date(ano, mes, 1)
    fim = inicio.replace(day=monthrange(ano, mes)[1])
    periodo = f"Periodo: {inicio:%d/%m/%Y} ate {fim:%d/%m/%Y}"
    titulo = f"{tipos[tipo]} - {MESES_PT[mes - 1]} {ano}"

    if tipo == "receita":
        parcelas = filtrar_parcelas_empresa(Parcela.objects.filter(
            venda__evento__isnull=False,
            data_pagamento__range=(inicio, fim),
        ).select_related("venda", "venda__cliente"), request)
        adiantamentos = (
            filtrar_empresa(Evento.objects.filter(
                venda__isnull=False,
                adiantamento__gt=0,
                adiantamento_pago=True,
                venda__data_venda__range=(inicio, fim),
            ), request)
            .exclude(venda__status="cancelado")
            .select_related("cliente", "venda")
        )
        total_parcelas = parcelas.aggregate(total=Sum("valor_recebido"))["total"] or Decimal("0.00")
        total_adiantamentos = adiantamentos.aggregate(total=Sum("adiantamento"))["total"] or Decimal("0.00")
        total = total_parcelas + total_adiantamentos
        linhas = [
            [
                parcela.venda.cliente.nome,
                parcela.venda.titulo,
                f"Parcela {parcela.numero}",
                parcela.data_pagamento.strftime("%d/%m/%Y") if parcela.data_pagamento else "",
                f"R$ {total_brl(parcela.valor_recebido)}",
            ]
            for parcela in parcelas
        ]
        linhas += [
            [
                evento.cliente.nome if evento.cliente else evento.nome,
                evento.venda.titulo if evento.venda else evento.nome,
                "Adiantamento",
                evento.venda.data_venda.strftime("%d/%m/%Y") if evento.venda else "",
                f"R$ {total_brl(evento.adiantamento)}",
            ]
            for evento in adiantamentos
        ]
        cabecalho = ["Cliente", "Venda", "Parcela", "Pagamento", "Valor"]
        resumo = f"Total recebido: R$ {total_brl(total)}"
    elif tipo == "despesas":
        despesas = filtrar_empresa(Despesa.objects.filter(filtro_data_financeira_despesa(inicio, fim)), request).order_by(
            "vencimento", "data", "descricao"
        )
        total = despesas.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
        linhas = [
            [
                despesa.descricao,
                despesa.categoria or "Sem categoria",
                data_financeira_despesa(despesa).strftime("%d/%m/%Y"),
                despesa.get_status_display(),
                f"R$ {total_brl(despesa.valor)}",
            ]
            for despesa in despesas
        ]
        cabecalho = ["Descricao", "Categoria", "Data financeira", "Status", "Valor"]
        resumo = f"Total de despesas: R$ {total_brl(total)}"
    elif tipo == "eventos":
        eventos = filtrar_empresa(Evento.objects.filter(data_festa__range=(inicio, fim)), request).select_related("cliente", "venda")
        linhas = [
            [
                evento.nome,
                evento.get_tipo_evento_display() if evento.tipo_evento else "Evento",
                evento.data_festa.strftime("%d/%m/%Y") if evento.data_festa else "",
                evento.cliente.nome if evento.cliente else "",
                f"R$ {total_brl(evento.valor_cobrado)}",
            ]
            for evento in eventos
        ]
        cabecalho = ["Evento", "Tipo", "Data", "Cliente", "Valor"]
        resumo = f"Total de eventos: {eventos.count()}"
    elif tipo == "vendas":
        vendas = (
            filtrar_empresa(Venda.objects.filter(evento__isnull=False), request)
            .exclude(status="cancelado")
            .filter(data_venda__range=(inicio, fim))
            .select_related("cliente")
        )
        total = vendas.aggregate(total=Sum("valor_total"))["total"] or Decimal("0.00")
        linhas = [
            [
                venda.cliente.nome,
                venda.titulo,
                venda.data_venda.strftime("%d/%m/%Y"),
                venda.get_status_display(),
                f"R$ {total_brl(venda.valor_total)}",
            ]
            for venda in vendas
        ]
        cabecalho = ["Cliente", "Venda", "Data", "Status", "Valor"]
        resumo = f"Total vendido: R$ {total_brl(total)}"
    else:
        eventos = filtrar_empresa(Evento.objects.filter(
            Q(criado_em__date__range=(inicio, fim)) | Q(atualizado_em__date__range=(inicio, fim))
        ), request).distinct().select_related("cliente", "venda")
        linhas = [
            [
                evento.nome,
                evento.get_tipo_evento_display() if evento.tipo_evento else "Evento",
                evento.data_festa.strftime("%d/%m/%Y") if evento.data_festa else "",
                evento.cliente.nome if evento.cliente else "",
                f"R$ {total_brl(evento.valor_cobrado)}",
            ]
            for evento in eventos
        ]
        cabecalho = ["Evento", "Tipo", "Data festa", "Cliente", "Valor"]
        resumo = f"Total de eventos recentes: {eventos.count()}"

    response = HttpResponse(
        gerar_pdf_relatorio_simples(titulo, periodo, resumo, cabecalho, linhas),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = f'inline; filename="relatorio_{tipo}_{ano}_{mes:02d}.pdf"'
    return response


def evento_form(request, pk=None):
    evento = get_object_or_404(filtrar_empresa(Evento.objects, request), pk=pk) if pk else None
    form = EventoForm(request.POST or None, instance=evento, empresa=empresa_atual(request))
    parcelas_form = parcelas_para_formulario(evento, request)
    parcelas_post = []
    if request.method == "POST" and form.is_valid():
        parcelas_post = parcelas_do_request(request, form)
    if request.method == "POST" and form.is_valid() and parcelas_post:
        acao = request.POST.get("acao") or "salvar"
        evento = form.save()
        aplicar_parcelas_evento(evento, parcelas_post)
        if acao == "gerar_contrato":
            form.criar_documento_evento(evento)
            messages.success(request, "Evento salvo. Contrato gerado no painel de documentos.")
            return redirect("documentos")
        messages.success(request, "Evento salvo com sucesso.")
        if request.GET.get("proximo") == "cliente" and evento.cliente_id:
            oportunidade_id = request.GET.get("oportunidade")
            if oportunidade_id:
                filtrar_empresa(Oportunidade.objects.filter(pk=oportunidade_id), request).update(cliente=evento.cliente, atualizado_em=timezone.now())
            messages.success(request, "Cliente criado ou atualizado a partir do evento.")
            return redirect("cliente_editar", pk=evento.cliente_id)
        return redirect("eventos")
    contrato_preview_template = CONTRATO_FESTA_INFANTIL_TEMPLATE
    if evento:
        documento = evento.documentos.order_by("-criado_em").first()
        if documento and documento.conteudo_contrato:
            contrato_preview_template = documento.conteudo_contrato
    return render(
        request,
        "crm/evento_form.html",
        {
            "form": form,
            "titulo": "Evento",
            "voltar": "eventos",
            "contrato_preview_template": contrato_preview_template,
            "parcelas_form": parcelas_form,
        },
    )


def evento_excluir(request, pk):
    evento = get_object_or_404(filtrar_empresa(Evento.objects, request), pk=pk)
    if request.method == "POST":
        evento.delete()
        messages.success(request, "Evento excluido.")
        return redirect("eventos")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": evento, "voltar": "eventos"})


def tarefa_form(request, pk=None):
    tarefa = get_object_or_404(filtrar_empresa(Tarefa.objects, request), pk=pk) if pk else None
    form = TarefaForm(request.POST or None, instance=tarefa)
    empresa = empresa_atual(request)
    if empresa:
        form.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa)
        form.fields["evento"].queryset = Evento.objects.filter(empresa=empresa)
    if request.method == "POST" and form.is_valid():
        tarefa = form.save(commit=False)
        atribuir_empresa(tarefa, request)
        tarefa.save()
        messages.success(request, "Tarefa salva com sucesso.")
        return redirect("agenda")
    return render(request, "crm/form.html", {"form": form, "titulo": "Tarefa ou trabalho", "voltar": "agenda"})


def tarefa_excluir(request, pk):
    tarefa = get_object_or_404(filtrar_empresa(Tarefa.objects, request), pk=pk)
    if request.method == "POST":
        tarefa.delete()
        messages.success(request, "Tarefa excluida.")
        return redirect("agenda")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": tarefa, "voltar": "agenda"})


def documentos(request):
    docs = filtrar_empresa(Documento.objects.select_related("cliente", "evento"), request)
    return render(request, "crm/documentos.html", {"documentos": docs})


def clientes_exportar_planilha(request):
    conteudo = montar_xlsx_clientes(filtrar_empresa(Cliente.objects.all(), request))
    response = HttpResponse(
        conteudo,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="clientes.xlsx"'
    return response


def clientes_importar_planilha(request):
    if request.method != "POST":
        return redirect("clientes")

    arquivo = request.FILES.get("planilha")
    if not arquivo:
        messages.error(request, "Selecione uma planilha para importar.")
        return redirect("clientes")

    try:
        if arquivo.name.lower().endswith(".csv"):
            linhas = ler_linhas_csv(arquivo)
        elif arquivo.name.lower().endswith(".xlsx"):
            linhas = ler_linhas_xlsx(arquivo)
        else:
            messages.error(request, "Envie uma planilha .xlsx ou .csv.")
            return redirect("clientes")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, ET.ParseError, KeyError, IndexError) as exc:
        messages.error(request, f"Nao foi possivel ler a planilha: {exc}")
        return redirect("clientes")

    if not linhas:
        messages.warning(request, "A planilha esta vazia.")
        return redirect("clientes")

    cabecalho = [normalizar_cabecalho(coluna) for coluna in linhas[0]]
    campos_por_rotulo = {normalizar_cabecalho(rotulo): campo for campo, rotulo in CLIENTE_PLANILHA_CAMPOS}
    indices = {campos_por_rotulo[nome]: indice for indice, nome in enumerate(cabecalho) if nome in campos_por_rotulo}
    if "nome" not in indices:
        messages.error(request, "A planilha precisa ter uma coluna Nome.")
        return redirect("clientes")

    criados = 0
    atualizados = 0
    ignorados = 0
    with transaction.atomic():
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
                cliente = filtrar_empresa(Cliente.objects.filter(email__iexact=email), request).first()
            if not cliente:
                cliente = filtrar_empresa(Cliente.objects.filter(nome__iexact=nome), request).first()

            data_evento = ler_data_planilha(dados.get("data_evento", ""))
            proxima_oportunidade = calcular_proxima_oportunidade(data_evento)

            valores = {
                "nome": nome,
                "empresa": empresa_atual(request),
                "telefone": dados.get("telefone", ""),
                "email": email,
                "origem": dados.get("origem", ""),
                "tipo_evento": dados.get("tipo_evento", ""),
                "data_evento": data_evento,
                "proxima_oportunidade": proxima_oportunidade,
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
    return redirect("clientes")


def documento_form(request, pk=None):
    documento = get_object_or_404(filtrar_empresa(Documento.objects, request), pk=pk) if pk else None
    initial = {}
    if not documento:
        evento_id = request.GET.get("evento")
        if evento_id:
            evento = get_object_or_404(filtrar_empresa(Evento.objects.select_related("cliente"), request), pk=evento_id)
            initial = {
                "evento": evento,
                "cliente": evento.cliente,
                "titulo": f"Contrato - {evento.nome}",
                "contato_whatsapp": evento.contato or (evento.cliente.telefone if evento.cliente else ""),
                "contato_email": evento.cliente.email if evento.cliente else "",
                "data_limite": evento.data_festa,
            }
    form = DocumentoForm(request.POST or None, request.FILES or None, instance=documento, initial=initial)
    empresa = empresa_atual(request)
    if empresa:
        form.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa)
        form.fields["evento"].queryset = Evento.objects.filter(empresa=empresa)
    if request.method == "POST" and form.is_valid():
        documento = form.save(commit=False)
        atribuir_empresa(documento, request)
        if documento.evento_id and not documento.empresa_id:
            documento.empresa = documento.evento.empresa
        if documento.cliente_id and not documento.empresa_id:
            documento.empresa = documento.cliente.empresa
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
        elif documento.status == "rascunho":
            documento.status = "pendente"
        documento.save()
        messages.success(request, "Documento salvo. Agora ele pode ser enviado ao cliente.")
        return redirect("documentos")
    return render(request, "crm/documento_form.html", {"form": form, "documento": documento})


def documento_excluir(request, pk):
    documento = get_object_or_404(filtrar_empresa(Documento.objects, request), pk=pk)
    if request.method == "POST":
        documento.delete()
        messages.success(request, "Documento excluido.")
        return redirect("documentos")
    return render(request, "crm/confirmar_exclusao.html", {"objeto": documento, "voltar": "documentos"})


def documento_enviar(request, pk):
    documento = get_object_or_404(filtrar_empresa(Documento.objects, request), pk=pk)
    if request.method != "POST":
        return redirect("documentos")

    if documento.status == "assinado":
        messages.warning(request, "Documento ja esta marcado como assinado. Envio nao realizado.")
        return redirect("documentos")
    if documento.status == "rascunho":
        messages.warning(request, "Revise e salve o contrato antes de enviar ao cliente.")
        return redirect("documento_editar", pk=documento.pk)

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
    documento = get_object_or_404(filtrar_empresa(Documento.objects, request), pk=pk)
    if documento.status == "rascunho":
        messages.warning(request, "Revise e salve o contrato antes de abrir o lembrete pelo WhatsApp.")
        return redirect("documento_editar", pk=documento.pk)
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
    documento = get_object_or_404(filtrar_empresa(Documento.objects, request), pk=pk)
    response = HttpResponse(gerar_pdf_documento(documento), content_type="application/pdf")
    disposition = request.GET.get("download")
    modo = "attachment" if disposition == "1" else "inline"
    response["Content-Disposition"] = f'{modo}; filename="{nome_pdf_documento(documento)}"'
    return response
