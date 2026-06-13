from calendar import monthrange
from io import BytesIO
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cliente, Despesa, Documento, Empresa, Evento, Oportunidade, Parcela, PerfilUsuario, Tarefa, Venda
from .views import ler_linhas_xlsx


class EventoDocumentoFlowTests(TestCase):
    def dados_evento(self):
        return {
            "nome": "Maria Silva",
            "email": "maria@example.com",
            "tipo_evento": "aniversario_infantil",
            "data_festa": "2026-07-10",
            "horario": "15:00",
            "contato": "(85) 99999-0000",
            "local_evento": "Buffet Central",
            "em_buffet": "on",
            "valor_cobrado": "1200,00",
            "forma_pagamento": "pix",
            "quantidade_parcelas": "1",
            "primeira_parcela": "2026-06-10",
            "parcela_numero": ["1"],
            "parcela_valor": ["1200,00"],
            "parcela_vencimento": ["2026-06-10"],
            "observacoes": "Contrato automatico",
        }

    def test_salvar_evento_nao_gera_documento_automaticamente(self):
        response = self.client.post(reverse("evento_novo"), self.dados_evento())

        evento = Evento.objects.get(nome="Maria Silva")
        self.assertFalse(Documento.objects.filter(evento=evento).exists())
        self.assertRedirects(response, reverse("eventos"))

    def test_gerar_contrato_cria_documento_e_vai_para_documentos(self):
        dados = self.dados_evento()
        dados["acao"] = "gerar_contrato"

        response = self.client.post(reverse("evento_novo"), dados)

        evento = Evento.objects.get(nome="Maria Silva")
        documento = Documento.objects.get(evento=evento)
        self.assertEqual(documento.status, "rascunho")
        self.assertEqual(documento.cliente, evento.cliente)
        self.assertRedirects(response, reverse("documentos"))

    def test_formulario_evento_exibe_campos_e_previa_do_contrato(self):
        response = self.client.get(reverse("evento_novo"))

        self.assertContains(response, "contract-workspace")
        self.assertContains(response, "CONTRATO DE SERVICO")
        self.assertContains(response, "id_cpf_contratante")
        self.assertContains(response, "id_descricao_servico")
        self.assertContains(response, "parcela_numero")
        self.assertContains(response, "parcela_valor")
        self.assertContains(response, "parcela_vencimento")
        self.assertContains(response, "id_valor_restante_contrato")
        self.assertContains(response, 'name="valor_cobrado"')
        self.assertNotContains(response, 'name="valor_cobrado" value="0,00"')

    def test_evento_vindo_de_lead_fechado_mostra_valor_fechado(self):
        oportunidade = Oportunidade.objects.create(
            nome_lead="Lead Fechado",
            titulo="Instagram",
            tipo_evento="aniversario_infantil",
            etapa="negociacao",
            valor_estimado="500.00",
            valor_negociado="750.00",
            data_festa="2026-08-12",
            contato="(85) 99999-1111",
        )

        response = self.client.get(reverse("oportunidade_mover", args=[oportunidade.pk, "fechado"]), follow=True)

        self.assertContains(response, 'name="valor_cobrado"')
        self.assertContains(response, 'value="750,00"')

    def test_lista_clientes_conta_apenas_vendas_de_eventos(self):
        self.client.post(reverse("evento_novo"), self.dados_evento())
        cliente = Cliente.objects.get(nome="Maria Silva")
        Venda.objects.create(
            cliente=cliente,
            titulo="Venda avulsa",
            valor_total="100.00",
            status="pago",
            forma_pagamento="pix",
            condicao_pagamento="avista",
            quantidade_parcelas=1,
        )

        response = self.client.get(reverse("clientes"))

        cliente_listado = response.context["clientes"].get(pk=cliente.pk)
        self.assertEqual(cliente_listado.total_vendas, 1)

    def test_contrato_usa_informacoes_preenchidas_no_evento(self):
        dados = self.dados_evento()
        dados.update(
            {
                "cpf_contratante": "123.456.789-00",
                "endereco_contratante": "Rua das Flores, 100",
                "aniversariante": "Theo Silva",
                "idade": "5 anos",
                "horario_fim": "18:00",
                "descricao_servico": "Cobertura fotografica completa com link digital.",
                "adiantamento": "300,00",
                "parcela_valor": ["900,00"],
                "autoriza_uso_imagem": "on",
            }
        )

        dados["acao"] = "gerar_contrato"
        self.client.post(reverse("evento_novo"), dados)

        documento = Documento.objects.select_related("evento", "cliente").get()
        contrato = documento.contrato_renderizado()
        self.assertIn("CPF: 123.456.789-00", contrato)
        self.assertIn("ENDERECO: Rua das Flores, 100", contrato)
        self.assertIn("NOME DO ANIVERSARIANTE: Theo Silva", contrato)
        self.assertIn("IDADE: 5 anos", contrato)
        self.assertIn("HORARIO: 15:00 as 18:00", contrato)
        self.assertIn("Cobertura fotografica completa com link digital.", contrato)
        self.assertIn("ADIANTAMENTO: R$ 300,00", contrato)
        self.assertIn("RESTANTE: R$ 900,00", contrato)

    def test_formulario_salva_parcelas_informadas_no_contrato(self):
        dados = self.dados_evento()
        dados.update(
            {
                "forma_pagamento": "pix",
                "quantidade_parcelas": "2",
                "parcela_numero": ["1", "2"],
                "parcela_valor": ["500,00", "700,00"],
                "parcela_vencimento": ["2026-06-10", "2026-07-10"],
            }
        )

        self.client.post(reverse("evento_novo"), dados)

        parcelas = list(Parcela.objects.order_by("numero"))
        self.assertEqual(len(parcelas), 2)
        self.assertEqual(parcelas[0].numero, 1)
        self.assertEqual(str(parcelas[0].valor), "500.00")
        self.assertEqual(parcelas[0].vencimento.isoformat(), "2026-06-10")
        self.assertEqual(parcelas[1].numero, 2)
        self.assertEqual(str(parcelas[1].valor), "700.00")
        self.assertEqual(parcelas[1].vencimento.isoformat(), "2026-07-10")

    def test_parcelas_devem_somar_valor_restante_apos_adiantamento(self):
        dados = self.dados_evento()
        dados.update(
            {
                "valor_cobrado": "800,00",
                "adiantamento": "200,00",
                "forma_pagamento": "boleto",
                "quantidade_parcelas": "3",
                "parcela_numero": ["1", "2", "3"],
                "parcela_valor": ["200,00", "200,00", "200,00"],
                "parcela_vencimento": ["2026-06-26", "2026-07-26", "2026-08-26"],
            }
        )

        response = self.client.post(reverse("evento_novo"), dados)

        self.assertRedirects(response, reverse("eventos"))
        parcelas = list(Parcela.objects.order_by("numero"))
        self.assertEqual(len(parcelas), 3)
        self.assertEqual(sum((parcela.valor for parcela in parcelas)), 600)

    def test_documento_rascunho_nao_envia_antes_de_salvar_revisao(self):
        dados = self.dados_evento()
        dados["acao"] = "gerar_contrato"
        self.client.post(reverse("evento_novo"), dados)
        documento = Documento.objects.get()

        response = self.client.post(reverse("documento_enviar", args=[documento.pk]))

        documento.refresh_from_db()
        self.assertEqual(documento.status, "rascunho")
        self.assertRedirects(response, reverse("documento_editar", args=[documento.pk]))

    def test_salvar_documento_revisado_libera_envio_e_pdf_usa_texto_editado(self):
        dados = self.dados_evento()
        dados["acao"] = "gerar_contrato"
        self.client.post(reverse("evento_novo"), dados)
        documento = Documento.objects.select_related("cliente", "evento").get()
        conteudo = "CONTRATO REVISADO PARA {{ cliente_nome }}\nClausula especial editada."

        response = self.client.post(
            reverse("documento_editar", args=[documento.pk]),
            {
                "cliente": documento.cliente_id,
                "evento": documento.evento_id,
                "titulo": documento.titulo,
                "status": documento.status,
                "contato_whatsapp": documento.contato_whatsapp,
                "contato_email": documento.contato_email,
                "forma_envio": documento.forma_envio,
                "enviado_em": "",
                "assinado_em": "",
                "data_limite": documento.data_limite.isoformat(),
                "conteudo_contrato": conteudo,
                "observacoes": documento.observacoes,
            },
        )

        documento.refresh_from_db()
        self.assertRedirects(response, reverse("documentos"))
        self.assertEqual(documento.status, "pendente")

        pdf_response = self.client.get(reverse("documento_pdf", args=[documento.pk]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn(b"Clausula especial editada.", pdf_response.content)


class ClientePlanilhaTests(TestCase):
    def test_planilha_exportada_nao_pede_proxima_oportunidade(self):
        response = self.client.get(reverse("clientes_exportar_planilha"))

        linhas = ler_linhas_xlsx(BytesIO(response.content))

        self.assertEqual(response.status_code, 200)
        self.assertIn("Data do evento", linhas[0])
        self.assertNotIn("Proxima oportunidade", linhas[0])

    def test_importacao_calcula_proxima_oportunidade_pela_data_do_evento(self):
        conteudo = "Nome,Telefone,Email,Origem,Tipo de evento,Data do evento,Observacoes\n"
        conteudo += "Marcos Torres,8595989898,marcos@teste.com,Instagram,Aniversario,30/05/2026,Cliente importado\n"
        arquivo = SimpleUploadedFile("clientes.csv", conteudo.encode("utf-8"), content_type="text/csv")

        response = self.client.post(reverse("clientes_importar_planilha"), {"planilha": arquivo})

        cliente = Cliente.objects.get(nome="Marcos Torres")
        self.assertRedirects(response, reverse("clientes"))
        self.assertEqual(cliente.data_evento.isoformat(), "2026-05-30")
        self.assertEqual(cliente.proxima_oportunidade.isoformat(), "2027-03-30")


class AgendaTests(TestCase):
    def test_mini_calendario_exibe_marcadores_coloridos_por_tipo(self):
        Tarefa.objects.create(titulo="Trabalho teste", tipo="trabalho", data="2026-05-24")
        Tarefa.objects.create(titulo="Reuniao teste", tipo="reuniao", data="2026-05-24")

        response = self.client.get(reverse("agenda"), {"data": "2026-05-24"})

        self.assertContains(response, "mini-day-marker tone-trabalho")
        self.assertContains(response, "mini-day-marker tone-reuniao")


class DespesasTests(TestCase):
    def test_despesas_sao_agrupadas_por_mes(self):
        Despesa.objects.create(descricao="Aluguel", categoria="Fixo", valor="500.00", data="2026-05-05")
        Despesa.objects.create(descricao="Album", categoria="Produto", valor="300.00", data="2026-06-10")

        response = self.client.get(reverse("despesas"))

        self.assertContains(response, "Maio 2026")
        self.assertContains(response, "Junho 2026")
        self.assertContains(response, "Relatorio PDF")

    def test_despesa_paga_entra_no_mes_do_vencimento(self):
        Despesa.objects.create(
            descricao="VideoMake",
            categoria="Video",
            valor="150.00",
            data="2026-07-15",
            vencimento="2026-06-10",
            status="pago",
        )

        response = self.client.get(reverse("despesas"))

        grupos = response.context["grupos_despesas"]
        self.assertEqual(grupos[0]["titulo"], "Junho 2026")
        self.assertEqual(grupos[0]["total_valor"], Decimal("150.00"))

    def test_relatorio_pdf_despesas_mes(self):
        Despesa.objects.create(descricao="Aluguel", categoria="Fixo", valor="500.00", data="2026-05-05")

        response = self.client.get(reverse("despesas_relatorio_pdf", args=[2026, 5]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(b"Aluguel", response.content)

    def test_relatorio_pdf_usa_mes_do_vencimento(self):
        Despesa.objects.create(
            descricao="VideoMake",
            categoria="Video",
            valor="150.00",
            data="2026-07-15",
            vencimento="2026-06-10",
            status="pago",
        )

        response = self.client.get(reverse("despesas_relatorio_pdf", args=[2026, 6]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"VideoMake", response.content)

    def test_relatorio_pdf_card_despesas(self):
        Despesa.objects.create(
            descricao="VideoMake",
            categoria="Video",
            valor="150.00",
            data="2026-07-15",
            vencimento="2026-06-10",
            status="pago",
        )

        response = self.client.get(reverse("relatorios_pdf", args=["despesas"]), {"inicio": "2026-06-01", "fim": "2026-06-30"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(b"VideoMake", response.content)


class MultiEmpresaIsolationTests(TestCase):
    def test_cliente_nao_enxerga_dados_de_outra_empresa(self):
        empresa_a = Empresa.objects.create(nome="Empresa A")
        empresa_b = Empresa.objects.create(nome="Empresa B")
        Cliente.objects.create(nome="Cliente Empresa A", empresa=empresa_a)
        Cliente.objects.create(nome="Cliente Empresa B", empresa=empresa_b)
        user = User.objects.create_user(username="empresa_b", password="senha")
        PerfilUsuario.objects.create(user=user, empresa=empresa_b, papel="empresa_admin")
        self.client.force_login(user)

        response = self.client.get(reverse("clientes"))

        self.assertContains(response, "Cliente Empresa B")
        self.assertNotContains(response, "Cliente Empresa A")


class FinanceiroReceitasTests(TestCase):
    def criar_venda_com_parcela(self):
        cliente = Cliente.objects.create(nome="Cliente Parcial", telefone="85999990000")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            valor_total="600.00",
            status="pendente",
            forma_pagamento="boleto",
            condicao_pagamento="parcelado",
            quantidade_parcelas=3,
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda,
            nome="Cliente Parcial",
            tipo_evento="aniversario",
            valor_cobrado="600.00",
            forma_pagamento="boleto",
            quantidade_parcelas=3,
        )
        parcela = Parcela.objects.create(
            venda=venda,
            numero=1,
            valor="200.00",
            vencimento="2026-06-01",
            status="pendente",
        )
        return venda, parcela

    def test_baixa_parcial_mantem_valor_contratado_e_saldo_aberto(self):
        venda, parcela = self.criar_venda_com_parcela()

        response = self.client.post(
            reverse("parcela_marcar_pago", args=[parcela.pk]),
            {"valor_recebido": "150,00", "next": reverse("cobrancas")},
        )

        parcela.refresh_from_db()
        venda.refresh_from_db()
        self.assertRedirects(response, reverse("cobrancas"))
        self.assertEqual(parcela.status, "parcial")
        self.assertEqual(parcela.valor, Decimal("200.00"))
        self.assertEqual(parcela.valor_recebido, Decimal("150.00"))
        self.assertEqual(parcela.valor_em_aberto, Decimal("50.00"))
        self.assertEqual(venda.status, "pendente")

    def test_venda_so_fica_paga_quando_recebido_cobre_total_contratado(self):
        venda, parcela = self.criar_venda_com_parcela()
        Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="200.00",
            valor_recebido="200.00",
            vencimento="2026-07-01",
            data_pagamento="2026-06-03",
            status="pago",
        )
        Parcela.objects.create(
            venda=venda,
            numero=3,
            valor="200.00",
            valor_recebido="200.00",
            vencimento="2026-08-01",
            data_pagamento="2026-06-03",
            status="pago",
        )

        self.client.post(
            reverse("parcela_marcar_pago", args=[parcela.pk]),
            {"valor_recebido": "200,00", "next": reverse("cobrancas")},
        )

        venda.refresh_from_db()
        self.assertEqual(venda.status, "pago")

    def test_financeiro_mostra_evento_pix_parcelado_com_parcelas_abertas(self):
        cliente = Cliente.objects.create(nome="Antonio Silva", telefone="8501020305")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            valor_total="800.00",
            status="pendente",
            forma_pagamento="pix",
            condicao_pagamento="parcelado",
            quantidade_parcelas=3,
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda,
            nome="Antonio Silva",
            tipo_evento="aniversario",
            valor_cobrado="800.00",
            forma_pagamento="pix",
            quantidade_parcelas=3,
            data_festa="2026-08-15",
        )
        Parcela.objects.create(venda=venda, numero=1, valor="400.00", vencimento="2026-07-03", status="pendente")
        Parcela.objects.create(venda=venda, numero=2, valor="200.00", vencimento="2026-08-03", status="pendente")
        Parcela.objects.create(venda=venda, numero=3, valor="200.00", vencimento="2026-09-03", status="pendente")

        response = self.client.get(reverse("financeiro"))

        grupo_em_dia = next(grupo for grupo in response.context["grupos_financeiros"] if grupo["status_painel"] == "pendente")
        self.assertEqual(grupo_em_dia["total"], 1)
        self.assertEqual(grupo_em_dia["clientes"][0]["cliente"], cliente)

    def test_dashboard_contabiliza_adiantamento_como_receita_recebida(self):
        hoje = timezone.localdate()
        cliente = Cliente.objects.create(nome="Cliente Adiantamento")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            data_venda=hoje,
            valor_total="600.00",
            status="pendente",
            forma_pagamento="pix",
            condicao_pagamento="parcelado",
            quantidade_parcelas=1,
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda,
            nome="Cliente Adiantamento",
            tipo_evento="aniversario",
            valor_cobrado="600.00",
            forma_pagamento="pix",
            quantidade_parcelas=1,
            adiantamento="200.00",
            adiantamento_pago=True,
        )
        Parcela.objects.create(
            venda=venda,
            numero=1,
            valor="400.00",
            vencimento=hoje,
            status="pendente",
        )

        response = self.client.get(reverse("dashboard"))
        totais = response.context["totais"]

        self.assertEqual(totais["receitas_recebidas"], Decimal("200.00"))
        self.assertEqual(totais["receitas_a_receber"], Decimal("400.00"))
        self.assertEqual(totais["saldo_atual"], Decimal("200.00"))
        self.assertEqual(totais["saldo_previsto"], Decimal("600.00"))
        self.assertEqual(response.context["formas_pagamento"][0]["total"], Decimal("200.00"))

    def test_relatorio_receita_inclui_adiantamento_pago(self):
        hoje = timezone.localdate()
        cliente = Cliente.objects.create(nome="Cliente Relatorio")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            data_venda=hoje,
            valor_total="600.00",
            status="pendente",
            forma_pagamento="pix",
            condicao_pagamento="parcelado",
            quantidade_parcelas=1,
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda,
            nome="Cliente Relatorio",
            tipo_evento="aniversario",
            valor_cobrado="600.00",
            forma_pagamento="pix",
            quantidade_parcelas=1,
            adiantamento="200.00",
            adiantamento_pago=True,
        )

        response = self.client.get(
            reverse("relatorios_pdf", args=["receitas"]),
            {"inicio": hoje.replace(day=1).isoformat(), "fim": hoje.replace(day=monthrange(hoje.year, hoje.month)[1]).isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Adiantamento", response.content)
        self.assertIn(b"200,00", response.content)
