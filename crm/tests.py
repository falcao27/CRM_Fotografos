from calendar import monthrange
from datetime import date, timedelta
from importlib import import_module
from io import BytesIO
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
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
        self.assertContains(response, 'name="tem_album"')
        self.assertContains(response, 'name="album_tipo"')
        self.assertNotContains(response, 'name="valor_cobrado" value="0,00"')

    def test_formulario_evento_salva_tipo_album_e_data_limite(self):
        dados = self.dados_evento()
        dados.update(
            {
                "tem_album": "on",
                "album_tipo": "Linha Premium",
            }
        )

        response = self.client.post(reverse("evento_novo"), dados)

        evento = Evento.objects.get(nome="Maria Silva")
        self.assertRedirects(response, reverse("eventos"))
        self.assertTrue(evento.tem_album)
        self.assertEqual(evento.album_tipo, "Linha Premium")
        self.assertEqual(evento.album_data_recebimento, date(2027, 7, 10))

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

    def test_painel_edicao_usa_dia_seguinte_ao_evento(self):
        cliente = Cliente.objects.create(nome="Cliente Edicao")
        evento = Evento.objects.create(
            cliente=cliente,
            nome="Cliente Edicao",
            tipo_evento="aniversario",
            data_festa="2026-07-04",
            local_evento="Buffet Central",
            contato="85999990000",
        )

        response = self.client.get(reverse("edicao"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edicao")
        self.assertContains(response, "Julho 2026")
        self.assertContains(response, "Cliente Edicao")
        self.assertContains(response, "05/07/2026")
        self.assertContains(response, "Data da edicao")
        self.assertContains(response, "Data da Entrega ao Cliente")
        self.assertContains(response, "Status")
        self.assertContains(response, reverse("edicao_evento_editar", args=[evento.pk]))
        self.assertContains(response, "Buscar cliente, contato ou pais")

    def test_painel_edicao_nao_mostra_evento_no_dia_do_evento(self):
        hoje = timezone.localdate()
        cliente = Cliente.objects.create(nome="Cliente Hoje")
        Evento.objects.create(
            cliente=cliente,
            nome="Cliente Hoje",
            tipo_evento="aniversario",
            data_festa=hoje,
        )
        Evento.objects.create(
            cliente=cliente,
            nome="Cliente Ontem",
            tipo_evento="aniversario",
            data_festa=hoje - timedelta(days=1),
        )

        response = self.client.get(reverse("edicao"))

        self.assertContains(response, "Cliente Ontem")
        self.assertNotContains(response, "Cliente Hoje")

    def test_formulario_edicao_salva_dados_operacionais(self):
        evento = Evento.objects.create(
            nome="Cliente Edicao Form",
            tipo_evento="aniversario",
            data_festa="2026-07-04",
            contato="85999990000",
            aniversariante="Ana",
        )

        response = self.client.post(
            reverse("edicao_evento_editar", args=[evento.pk]),
            {
                "edicao_data": "2026-07-06",
                "edicao_cliente_pais": "Pais da Ana",
                "edicao_contato": "8511111111",
                "edicao_aniversariantes": "Ana",
                "edicao_tipo_servico": "Aniversario",
                "edicao_backup": "on",
                "edicao_selecao": "on",
                "edicao_editado": "on",
                "edicao_data_entrega": "2026-07-20",
                "edicao_status": "finalizado",
            },
        )

        evento.refresh_from_db()
        self.assertRedirects(response, reverse("edicao"))
        self.assertEqual(evento.edicao_cliente_pais, "Pais da Ana")
        self.assertEqual(evento.edicao_status, "finalizado")
        self.assertTrue(evento.edicao_backup)
        self.assertTrue(evento.edicao_selecao)
        self.assertTrue(evento.edicao_editado)

    def test_painel_album_mostra_apenas_eventos_com_album(self):
        cliente = Cliente.objects.create(nome="Cliente Album")
        evento = Evento.objects.create(
            cliente=cliente,
            nome="Cliente Album",
            tipo_evento="aniversario",
            data_festa="2026-07-04",
            tem_album=True,
            album_tipo="Premium",
            album_data_envio="2026-07-10",
            album_data_recebimento="2026-07-20",
            contato="85999990000",
        )
        Evento.objects.create(
            cliente=cliente,
            nome="Cliente Sem Album",
            tipo_evento="aniversario",
            data_festa="2026-07-05",
            tem_album=False,
        )

        response = self.client.get(reverse("album"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Album")
        self.assertContains(response, "Cliente Album")
        self.assertContains(response, "Tipo de Album")
        self.assertContains(response, "Data Final para recebimento de Fotos do Album")
        self.assertContains(response, "Data de Envio")
        self.assertContains(response, "Premium")
        self.assertContains(response, "10/07/2026")
        self.assertContains(response, "20/07/2026")
        self.assertContains(response, "wa.me")
        self.assertContains(response, "Enviar lembrete mensal pelo WhatsApp")
        self.assertContains(response, reverse("album_evento_editar", args=[evento.pk]))
        self.assertNotContains(response, "Cliente Sem Album")

    def test_painel_album_nao_mostra_evento_no_dia_do_evento(self):
        hoje = timezone.localdate()
        cliente = Cliente.objects.create(nome="Cliente Album Hoje")
        Evento.objects.create(
            cliente=cliente,
            nome="Album Hoje",
            tipo_evento="aniversario",
            data_festa=hoje,
            tem_album=True,
        )
        Evento.objects.create(
            cliente=cliente,
            nome="Album Ontem",
            tipo_evento="aniversario",
            data_festa=hoje - timedelta(days=1),
            tem_album=True,
        )

        response = self.client.get(reverse("album"))

        self.assertContains(response, "Album Ontem")
        self.assertNotContains(response, "Album Hoje")

    def test_formulario_album_salva_dados_do_cabecario(self):
        evento = Evento.objects.create(
            nome="Cliente Album Form",
            tipo_evento="aniversario",
            data_festa="2026-07-04",
            tem_album=True,
        )

        response = self.client.post(
            reverse("album_evento_editar", args=[evento.pk]),
            {
                "nome": "Cliente Album Atualizado",
                "tipo_evento": "aniversario",
                "album_tipo": "Linha Premium",
                "album_data_envio": "2026-07-12",
                "album_data_recebimento": "2026-07-30",
                "album_status": "finalizado",
            },
        )

        evento.refresh_from_db()
        self.assertRedirects(response, reverse("album"))
        self.assertEqual(evento.nome, "Cliente Album Atualizado")
        self.assertEqual(evento.album_tipo, "Linha Premium")
        self.assertEqual(evento.album_status, "finalizado")

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

    def test_pagamento_cartao_exige_valor_recebido_da_maquina(self):
        dados = self.dados_evento()
        dados.update(
            {
                "forma_pagamento": "cartao",
                "parcela_valor": ["1200,00"],
            }
        )

        response = self.client.post(reverse("evento_novo"), dados)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe o valor real recebido da maquina.")
        self.assertFalse(Evento.objects.filter(nome="Maria Silva").exists())

    def test_pagamento_cartao_usa_valor_recebido_no_financeiro_receitas_e_dashboard(self):
        dados = self.dados_evento()
        dados.update(
            {
                "forma_pagamento": "cartao",
                "valor_recebido_cartao": "1150,00",
                "pagamento_recebido": "on",
                "parcela_valor": ["1150,00"],
            }
        )

        response = self.client.post(reverse("evento_novo"), dados)

        self.assertRedirects(response, reverse("eventos"))
        evento = Evento.objects.select_related("venda").get(nome="Maria Silva")
        parcela = evento.venda.parcelas.get()
        self.assertEqual(evento.valor_cobrado, Decimal("1200.00"))
        self.assertEqual(evento.valor_recebido_cartao, Decimal("1150.00"))
        self.assertEqual(evento.venda.valor_total, Decimal("1150.00"))
        self.assertEqual(parcela.valor, Decimal("1150.00"))
        self.assertEqual(parcela.valor_recebido, Decimal("1150.00"))

        receitas_response = self.client.get(reverse("receitas"))
        self.assertEqual(receitas_response.context["grupos_receitas"][0]["total_valor"], Decimal("1150.00"))

        dashboard_response = self.client.get(reverse("dashboard"), {"receita": "todos"})
        self.assertEqual(dashboard_response.context["totais"]["receita_total"], Decimal("1150.00"))
        self.assertEqual(dashboard_response.context["totais"]["receita_paga"], Decimal("1150.00"))

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
        self.assertEqual(len(parcelas), 4)
        self.assertEqual(parcelas[0].valor, Decimal("200.00"))
        self.assertEqual(parcelas[0].vencimento.isoformat(), "2026-06-10")
        self.assertEqual(sum((parcela.valor for parcela in parcelas[1:])), 600)

    def test_adiantamento_pago_nao_marca_parcela_restante_como_paga(self):
        dados = self.dados_evento()
        dados.update(
            {
                "nome": "Lia Nunes Benevides",
                "email": "linanunesb@gmail.com",
                "contato": "85992179292",
                "valor_cobrado": "600,00",
                "adiantamento": "300,00",
                "adiantamento_pago": "on",
                "forma_pagamento": "pix",
                "quantidade_parcelas": "1",
                "primeira_parcela": "2026-06-11",
                "parcela_numero": ["1"],
                "parcela_valor": ["300,00"],
                "parcela_vencimento": ["2026-07-25"],
            }
        )

        response = self.client.post(reverse("evento_novo"), dados)

        self.assertRedirects(response, reverse("eventos"))
        evento = Evento.objects.select_related("venda").get(nome="Lia Nunes Benevides")
        adiantamento = evento.venda.parcelas.get(numero=1)
        parcela = evento.venda.parcelas.get(numero=2)
        self.assertTrue(evento.adiantamento_pago)
        self.assertFalse(evento.pagamento_recebido)
        self.assertEqual(evento.venda.valor_total, Decimal("600.00"))
        self.assertEqual(evento.venda.valor_pago, Decimal("300.00"))
        self.assertEqual(evento.venda.valor_pendente, Decimal("300.00"))
        self.assertEqual(adiantamento.valor, Decimal("300.00"))
        self.assertEqual(adiantamento.valor_recebido, Decimal("300.00"))
        self.assertEqual(adiantamento.status, "pago")
        self.assertEqual(adiantamento.vencimento.isoformat(), "2026-06-11")
        self.assertEqual(parcela.valor, Decimal("300.00"))
        self.assertEqual(parcela.valor_recebido, Decimal("0.00"))
        self.assertEqual(parcela.status, "pendente")
        self.assertEqual(parcela.vencimento.isoformat(), "2026-07-25")
        self.assertIsNone(parcela.data_pagamento)

    def test_adiantamento_nao_pago_aparece_como_primeira_parcela_em_aberto(self):
        dados = self.dados_evento()
        dados.update(
            {
                "nome": "Lia Nunes Benevides",
                "valor_cobrado": "600,00",
                "adiantamento": "300,00",
                "forma_pagamento": "pix",
                "quantidade_parcelas": "1",
                "primeira_parcela": "2026-06-11",
                "parcela_numero": ["1"],
                "parcela_valor": ["300,00"],
                "parcela_vencimento": ["2026-07-25"],
            }
        )

        response = self.client.post(reverse("evento_novo"), dados)

        self.assertRedirects(response, reverse("eventos"))
        evento = Evento.objects.select_related("venda").get(nome="Lia Nunes Benevides")
        adiantamento = evento.venda.parcelas.get(numero=1)
        parcela = evento.venda.parcelas.get(numero=2)
        self.assertFalse(evento.adiantamento_pago)
        self.assertEqual(evento.venda.valor_pago, Decimal("0.00"))
        self.assertEqual(evento.venda.valor_pendente, Decimal("600.00"))
        self.assertEqual(adiantamento.valor, Decimal("300.00"))
        self.assertEqual(adiantamento.valor_recebido, Decimal("0.00"))
        self.assertEqual(adiantamento.status, "pendente")
        self.assertEqual(adiantamento.vencimento.isoformat(), "2026-06-11")
        self.assertEqual(parcela.valor, Decimal("300.00"))
        self.assertEqual(parcela.status, "pendente")
        self.assertEqual(parcela.vencimento.isoformat(), "2026-07-25")

    def test_salvar_evento_corrige_parcela_restante_marcada_como_paga_por_engano(self):
        dados = self.dados_evento()
        dados.update(
            {
                "nome": "Lia Nunes Benevides",
                "valor_cobrado": "600,00",
                "adiantamento": "300,00",
                "forma_pagamento": "pix",
                "quantidade_parcelas": "1",
                "primeira_parcela": "2026-06-11",
                "parcela_numero": ["1"],
                "parcela_valor": ["300,00"],
                "parcela_vencimento": ["2026-07-25"],
                "pagamento_recebido": "on",
            }
        )
        self.client.post(reverse("evento_novo"), dados)
        evento = Evento.objects.select_related("venda").get(nome="Lia Nunes Benevides")
        parcela = evento.venda.parcelas.get(numero=2)
        self.assertEqual(parcela.status, "pago")

        dados.pop("pagamento_recebido")
        dados["adiantamento_pago"] = "on"
        response = self.client.post(reverse("evento_editar", args=[evento.pk]), dados)

        parcela.refresh_from_db()
        evento.refresh_from_db()
        self.assertRedirects(response, reverse("eventos"))
        self.assertTrue(evento.adiantamento_pago)
        self.assertFalse(evento.pagamento_recebido)
        self.assertEqual(parcela.status, "pendente")
        self.assertEqual(parcela.valor_recebido, Decimal("0.00"))
        self.assertIsNone(parcela.data_pagamento)

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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEFAULT_FROM_EMAIL="crm@localhost")
    def test_envio_documento_por_email_mantem_assinatura_gov(self):
        cliente = Cliente.objects.create(nome="Cliente Email", email="cliente@example.com")
        documento = Documento.objects.create(
            cliente=cliente,
            titulo="Contrato Email",
            status="pendente",
            contato_email=cliente.email,
            contato_whatsapp="85999990000",
        )

        response = self.client.post(reverse("documento_enviar", args=[documento.pk]), {"canal": "email"})

        documento.refresh_from_db()
        self.assertRedirects(response, reverse("documentos"))
        self.assertEqual(documento.status, "enviado")
        self.assertEqual(documento.forma_envio, "email")
        self.assertTrue(documento.ultimo_envio_sucesso)

    def test_envio_documento_por_whatsapp_web_prepara_pdf_e_conversa(self):
        cliente = Cliente.objects.create(nome="Cliente WhatsApp", telefone="85999990000")
        documento = Documento.objects.create(
            cliente=cliente,
            titulo="Contrato WhatsApp",
            status="pendente",
            contato_whatsapp=cliente.telefone,
            contato_email="cliente@example.com",
        )

        response = self.client.post(reverse("documento_enviar", args=[documento.pk]), {"canal": "whatsapp_web"})

        documento.refresh_from_db()
        self.assertRedirects(response, reverse("documento_whatsapp_manual", args=[documento.pk]))
        self.assertEqual(documento.status, "enviado")
        self.assertEqual(documento.forma_envio, "whatsapp")
        self.assertIn("PDF real", documento.ultimo_envio_retorno)


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

    def test_evento_cria_trabalho_na_agenda_com_empresa(self):
        empresa = Empresa.objects.create(nome="Empresa Agenda")
        cliente = Cliente.objects.create(nome="Cliente Agenda", empresa=empresa)

        evento = Evento.objects.create(
            empresa=empresa,
            cliente=cliente,
            nome=cliente.nome,
            tipo_evento="aniversario",
            data_festa="2026-08-20",
            horario="16:00",
        )

        tarefa = Tarefa.objects.get(evento=evento)
        self.assertEqual(tarefa.empresa, empresa)
        self.assertEqual(tarefa.cliente, cliente)
        self.assertEqual(tarefa.tipo, "trabalho")
        self.assertEqual(tarefa.data.isoformat(), "2026-08-20")

    def test_tarefa_pode_usar_nome_avulso_sem_cliente(self):
        response = self.client.post(
            reverse("tarefa_nova"),
            {
                "cliente": "",
                "nome_contato": "Reuniao com decoradora",
                "evento": "",
                "titulo": "Alinhamento do evento",
                "tipo": "reuniao",
                "data": "2026-07-15",
                "hora": "10:30",
                "status": "pendente",
                "descricao": "Visita tecnica fora do cadastro.",
            },
        )

        tarefa = Tarefa.objects.get(titulo="Alinhamento do evento")
        self.assertRedirects(response, reverse("agenda"))
        self.assertIsNone(tarefa.cliente)
        self.assertEqual(tarefa.nome_contato, "Reuniao com decoradora")
        self.assertFalse(Cliente.objects.filter(nome="Reuniao com decoradora").exists())


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

    def test_despesas_filtra_apenas_pagas(self):
        Despesa.objects.create(descricao="Paga", categoria="Fixo", valor="500.00", data="2026-05-05", status="pago")
        Despesa.objects.create(descricao="Pendente", categoria="Fixo", valor="300.00", data="2026-05-06")

        response = self.client.get(reverse("despesas"), {"status": "pago"})

        grupos = response.context["grupos_despesas"]
        despesas = [despesa for grupo in grupos for despesa in grupo["despesas"]]
        self.assertEqual([despesa.descricao for despesa in despesas], ["Paga"])
        self.assertContains(response, 'option value="pago" selected')

    def test_despesas_exibe_categorias_dentro_do_mes(self):
        Despesa.objects.create(descricao="Aluguel", categoria="Fixo", valor="500.00", data="2026-05-05")
        Despesa.objects.create(descricao="Album", categoria="Produto", valor="300.00", data="2026-05-06")

        response = self.client.get(reverse("despesas"))

        grupos = response.context["grupos_despesas"]
        self.assertEqual(grupos[0]["categorias"], ["Fixo", "Produto"])
        self.assertEqual(grupos[0]["total_valor"], Decimal("800.00"))
        self.assertContains(response, "Todas as categorias")
        self.assertContains(response, 'data-expense-category-filter')
        self.assertContains(response, 'data-expense-summary')
        self.assertContains(response, 'data-value="300.00"')
        self.assertNotContains(response, 'select name="categoria"')

    def test_relatorio_pdf_despesas_filtra_categoria_e_pagas(self):
        Despesa.objects.create(
            descricao="Video pago",
            categoria="Video",
            valor="150.00",
            data="2026-06-10",
            status="pago",
        )
        Despesa.objects.create(
            descricao="Video pendente",
            categoria="Video",
            valor="180.00",
            data="2026-06-11",
        )
        Despesa.objects.create(
            descricao="Produto pago",
            categoria="Produto",
            valor="300.00",
            data="2026-06-12",
            status="pago",
        )

        response = self.client.get(
            reverse("despesas_relatorio_pdf", args=[2026, 6]),
            {"status": "pago", "categoria": "Video"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Video pago", response.content)
        self.assertNotIn(b"Video pendente", response.content)
        self.assertNotIn(b"Produto pago", response.content)

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

    def test_painel_receitas_agrupa_parcelas_do_financeiro_por_mes(self):
        venda, parcela = self.criar_venda_com_parcela()
        Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="200.00",
            valor_recebido="200.00",
            vencimento="2026-07-01",
            data_pagamento="2026-07-02",
            status="pago",
        )

        response = self.client.get(reverse("receitas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Receitas")
        self.assertContains(response, "Receitas separadas por mes")
        self.assertContains(response, "Todas as receitas")
        self.assertContains(response, "Relatorio PDF")
        self.assertContains(response, "Junho 2026")
        self.assertContains(response, "Julho 2026")
        self.assertContains(response, "Cliente Parcial - Aniversario")
        self.assertContains(response, "Aniversario")
        self.assertContains(response, "Parcela 1 de 2")
        self.assertContains(response, "Parcela 2 de 2")
        self.assertNotContains(response, "venc.")
        self.assertNotContains(response, "Proximas:")
        self.assertContains(response, "R$ 200,00")
        self.assertContains(response, 'href="/receitas/')

    def test_painel_receitas_mostra_e_ordena_por_primeiro_pagamento(self):
        cliente_tarde = Cliente.objects.create(nome="Cliente Tarde", telefone="85999990001")
        venda_tarde = Venda.objects.create(
            cliente=cliente_tarde,
            titulo="Evento Tarde",
            valor_total="300.00",
            status="pago",
            forma_pagamento="pix",
        )
        Evento.objects.create(
            cliente=cliente_tarde,
            venda=venda_tarde,
            nome="Cliente Tarde",
            tipo_evento="aniversario",
            valor_cobrado="300.00",
            forma_pagamento="pix",
            primeira_parcela=date(2026, 7, 10),
        )
        Parcela.objects.create(
            venda=venda_tarde,
            numero=1,
            valor="300.00",
            valor_recebido="300.00",
            vencimento=date(2026, 7, 10),
            data_pagamento=date(2026, 7, 10),
            status="pago",
        )
        cliente_cedo = Cliente.objects.create(nome="Cliente Cedo", telefone="85999990002")
        venda_cedo = Venda.objects.create(
            cliente=cliente_cedo,
            titulo="Evento Cedo",
            valor_total="300.00",
            status="pago",
            forma_pagamento="pix",
        )
        Evento.objects.create(
            cliente=cliente_cedo,
            venda=venda_cedo,
            nome="Cliente Cedo",
            tipo_evento="aniversario",
            valor_cobrado="300.00",
            forma_pagamento="pix",
            primeira_parcela=date(2026, 7, 1),
        )
        Parcela.objects.create(
            venda=venda_cedo,
            numero=1,
            valor="300.00",
            valor_recebido="300.00",
            vencimento=date(2026, 7, 1),
            data_pagamento=date(2026, 7, 2),
            status="pago",
        )

        response = self.client.get(reverse("receitas"))

        self.assertContains(response, "Data do Primeiro Pagamento")
        self.assertContains(response, "<th>Data do Primeiro Pagamento</th>", html=True)
        self.assertContains(response, "<th>Parcela</th>", html=True)
        conteudo = response.content.decode()
        self.assertLess(conteudo.index("<th>Data do Primeiro Pagamento</th>"), conteudo.index("<th>Parcela</th>"))
        receitas_julho = response.context["grupos_receitas"][0]["receitas"]
        self.assertEqual([receita.descricao for receita in receitas_julho], ["Cliente Cedo - Evento Cedo", "Cliente Tarde - Evento Tarde"])
        self.assertEqual([receita.data_primeiro_pagamento for receita in receitas_julho], [date(2026, 7, 1), date(2026, 7, 10)])

    def test_painel_receitas_filtra_apenas_pagas(self):
        venda, _parcela = self.criar_venda_com_parcela()
        Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="200.00",
            valor_recebido="200.00",
            vencimento="2026-07-01",
            data_pagamento="2026-07-02",
            status="pago",
        )

        response = self.client.get(reverse("receitas"), {"status": "pago"})

        grupos = response.context["grupos_receitas"]
        receitas = [receita for grupo in grupos for receita in grupo["receitas"]]
        self.assertEqual([receita.status for receita in receitas], ["pago"])
        self.assertContains(response, 'option value="pago" selected')

    def test_relatorio_pdf_receitas_mes(self):
        venda, _parcela = self.criar_venda_com_parcela()
        Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="200.00",
            valor_recebido="200.00",
            vencimento="2026-07-01",
            data_pagamento="2026-07-02",
            status="pago",
        )

        response = self.client.get(reverse("receitas_relatorio_pdf", args=[2026, 7]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(b"Cliente Par", response.content)
        self.assertIn(b"Data do Primeiro Pagamento", response.content)
        self.assertIn(b"Vencimento", response.content)

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

    def test_recebimento_maior_abate_proximas_parcelas_da_venda(self):
        cliente = Cliente.objects.create(nome="Cliente Excedente", telefone="85999990000")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            valor_total="1750.00",
            status="pendente",
            forma_pagamento="pix",
            condicao_pagamento="parcelado",
            quantidade_parcelas=2,
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda,
            nome="Cliente Excedente",
            tipo_evento="aniversario",
            valor_cobrado="1750.00",
            forma_pagamento="pix",
            quantidade_parcelas=2,
        )
        primeira = Parcela.objects.create(
            venda=venda,
            numero=1,
            valor="875.00",
            vencimento="2026-07-01",
            status="pendente",
        )
        segunda = Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="875.00",
            vencimento="2026-08-01",
            status="pendente",
        )

        response = self.client.post(
            reverse("parcela_marcar_pago", args=[primeira.pk]),
            {"valor_recebido": "900,00", "next": reverse("financeiro")},
        )

        primeira.refresh_from_db()
        segunda.refresh_from_db()
        venda.refresh_from_db()
        self.assertRedirects(response, reverse("financeiro"))
        self.assertEqual(primeira.status, "pago")
        self.assertEqual(primeira.valor, Decimal("875.00"))
        self.assertEqual(primeira.valor_recebido, Decimal("900.00"))
        self.assertEqual(primeira.valor_em_aberto, Decimal("0.00"))
        self.assertEqual(segunda.status_financeiro, "parcial")
        self.assertEqual(segunda.valor_recebido, Decimal("0.00"))
        self.assertEqual(segunda.valor_em_aberto, Decimal("850.00"))
        self.assertEqual(venda.valor_pago, Decimal("900.00"))
        self.assertEqual(venda.valor_pendente, Decimal("850.00"))
        self.assertEqual(venda.status, "pendente")

    def test_edicao_preserva_contrato_e_usa_recebido_maior_no_saldo(self):
        cliente = Cliente.objects.create(nome="Cliente Edicao", telefone="85999990000")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            valor_total="1750.00",
            status="pendente",
            forma_pagamento="pix",
            condicao_pagamento="parcelado",
            quantidade_parcelas=2,
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda,
            nome="Cliente Edicao",
            tipo_evento="aniversario",
            valor_cobrado="1750.00",
            forma_pagamento="pix",
            quantidade_parcelas=2,
        )
        primeira = Parcela.objects.create(
            venda=venda,
            numero=1,
            valor="875.00",
            vencimento="2026-07-01",
            lembrete_em="2026-07-03",
            status="pendente",
        )
        segunda = Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="875.00",
            vencimento="2026-08-02",
            lembrete_em="2026-08-02",
            status="pendente",
        )

        response = self.client.post(
            reverse("parcela_editar", args=[primeira.pk]),
            {
                "numero": "1",
                "valor": "900,00",
                "valor_recebido": "900,00",
                "total_parcelas_diluicao": "2",
                "vencimento": "2026-07-01",
                "data_pagamento": "2026-07-03",
                "status": "pago",
                "lembrete_em": "2026-07-03",
                "observacoes": "",
            },
        )

        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertRedirects(response, reverse("financeiro"))
        self.assertEqual(primeira.valor, Decimal("875.00"))
        self.assertEqual(primeira.valor_recebido, Decimal("900.00"))
        self.assertEqual(primeira.valor_em_aberto, Decimal("0.00"))
        self.assertEqual(segunda.valor, Decimal("875.00"))
        self.assertEqual(segunda.valor_recebido, Decimal("0.00"))
        self.assertEqual(segunda.valor_em_aberto, Decimal("850.00"))

    def test_migracao_repara_contrato_contaminado_por_valor_recebido(self):
        cliente = Cliente.objects.create(nome="Cliente Migracao", telefone="85999990000")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            valor_total="1750.00",
            status="pendente",
            forma_pagamento="pix",
            condicao_pagamento="parcelado",
            quantidade_parcelas=2,
        )
        primeira = Parcela.objects.create(
            venda=venda,
            numero=1,
            valor="900.00",
            valor_recebido="900.00",
            vencimento="2026-07-01",
            status="pago",
        )
        segunda = Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="875.00",
            vencimento="2026-08-02",
            status="pendente",
        )

        migracao = import_module("crm.migrations.0030_reparar_valor_contratado_parcelas")
        migracao.reparar_valores_contratados(django_apps, None)

        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primeira.valor, Decimal("875.00"))
        self.assertEqual(primeira.valor_recebido, Decimal("900.00"))
        self.assertEqual(segunda.valor, Decimal("875.00"))
        self.assertEqual(segunda.valor_em_aberto, Decimal("850.00"))

    def test_parcela_paga_com_valor_menor_acrescenta_na_proxima(self):
        cliente = Cliente.objects.create(nome="Cliente Menor Direto", telefone="85999990000")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            valor_total="1750.00",
            status="pendente",
            forma_pagamento="pix",
            condicao_pagamento="parcelado",
            quantidade_parcelas=2,
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda,
            nome="Cliente Menor Direto",
            tipo_evento="aniversario",
            valor_cobrado="1750.00",
            forma_pagamento="pix",
            quantidade_parcelas=2,
        )
        primeira = Parcela.objects.create(
            venda=venda,
            numero=1,
            valor="875.00",
            vencimento="2026-07-01",
            lembrete_em="2026-07-03",
            status="pendente",
        )
        segunda = Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="875.00",
            vencimento="2026-08-02",
            lembrete_em="2026-08-02",
            status="pendente",
        )

        response = self.client.post(
            reverse("parcela_editar", args=[primeira.pk]),
            {
                "numero": "1",
                "valor": "875,00",
                "valor_recebido": "800,00",
                "total_parcelas_diluicao": "2",
                "vencimento": "2026-07-01",
                "data_pagamento": "2026-07-03",
                "status": "pago",
                "lembrete_em": "2026-07-03",
                "observacoes": "",
            },
        )

        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertRedirects(response, reverse("financeiro"))
        self.assertEqual(primeira.valor, Decimal("875.00"))
        self.assertEqual(primeira.valor_recebido, Decimal("800.00"))
        self.assertEqual(primeira.valor_em_aberto, Decimal("0.00"))
        self.assertEqual(segunda.valor, Decimal("875.00"))
        self.assertEqual(segunda.valor_em_aberto, Decimal("950.00"))

    def test_edicao_dilui_recebimento_menor_em_novas_parcelas(self):
        cliente = Cliente.objects.create(nome="Cliente Menor", telefone="85999990000")
        venda = Venda.objects.create(
            cliente=cliente,
            titulo="Aniversario",
            valor_total="1750.00",
            status="pendente",
            forma_pagamento="pix",
            condicao_pagamento="parcelado",
            quantidade_parcelas=2,
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda,
            nome="Cliente Menor",
            tipo_evento="aniversario",
            valor_cobrado="1750.00",
            forma_pagamento="pix",
            quantidade_parcelas=2,
        )
        primeira = Parcela.objects.create(
            venda=venda,
            numero=1,
            valor="875.00",
            vencimento="2026-07-01",
            lembrete_em="2026-06-28",
            status="pendente",
        )
        segunda = Parcela.objects.create(
            venda=venda,
            numero=2,
            valor="875.00",
            vencimento="2026-08-01",
            lembrete_em="2026-07-29",
            status="pendente",
        )

        response = self.client.post(
            reverse("parcela_editar", args=[primeira.pk]),
            {
                "numero": "1",
                "valor": "875,00",
                "valor_recebido": "800,00",
                "diluir_saldo": "on",
                "total_parcelas_diluicao": "3",
                "vencimento": "2026-07-01",
                "data_pagamento": "2026-07-03",
                "status": "parcial",
                "lembrete_em": "2026-06-28",
                "observacoes": "",
            },
        )

        primeira.refresh_from_db()
        segunda.refresh_from_db()
        terceira = venda.parcelas.get(numero=3)
        venda.refresh_from_db()
        self.assertRedirects(response, reverse("financeiro"))
        self.assertEqual(primeira.status, "pago")
        self.assertEqual(primeira.valor, Decimal("875.00"))
        self.assertEqual(primeira.valor_recebido, Decimal("800.00"))
        self.assertEqual(segunda.valor, Decimal("400.00"))
        self.assertEqual(segunda.valor_em_aberto, Decimal("475.00"))
        self.assertEqual(terceira.valor, Decimal("475.00"))
        self.assertEqual(terceira.valor_em_aberto, Decimal("475.00"))
        self.assertEqual(venda.quantidade_parcelas, 3)
        self.assertEqual(venda.valor_pago, Decimal("800.00"))
        self.assertEqual(venda.valor_pendente, Decimal("950.00"))

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

    def test_editar_parcela_paga_preserva_recebido_maior_que_contratado(self):
        venda, parcela = self.criar_venda_com_parcela()
        parcela.valor = Decimal("300.00")
        parcela.valor_recebido = Decimal("1200.00")
        parcela.data_pagamento = timezone.localdate()
        parcela.status = "pago"
        parcela.save()

        response = self.client.post(
            reverse("parcela_editar", args=[parcela.pk]),
            {
                "numero": "1",
                "valor": "300,00",
                "valor_recebido": "1200,00",
                "vencimento": "2026-06-01",
                "data_pagamento": timezone.localdate().isoformat(),
                "status": "pago",
                "lembrete_em": "",
                "observacoes": "",
            },
        )

        parcela.refresh_from_db()
        venda.refresh_from_db()
        self.assertRedirects(response, reverse("financeiro"))
        self.assertEqual(parcela.status, "pago")
        self.assertEqual(parcela.valor, Decimal("300.00"))
        self.assertEqual(parcela.valor_recebido, Decimal("1200.00"))
        self.assertEqual(venda.valor_pago, Decimal("1200.00"))

    def test_editar_parcela_paga_para_pendente_limpa_pagamento(self):
        venda, parcela = self.criar_venda_com_parcela()
        evento = venda.evento
        venda.valor_total = Decimal("300.00")
        venda.status = "pago"
        venda.save()
        evento.pagamento_recebido = True
        evento.save()
        parcela.valor = Decimal("300.00")
        parcela.valor_recebido = Decimal("300.00")
        parcela.data_pagamento = timezone.localdate()
        parcela.status = "pago"
        parcela.save()

        response = self.client.post(
            reverse("parcela_editar", args=[parcela.pk]),
            {
                "numero": "1",
                "valor": "300,00",
                "valor_recebido": "300,00",
                "vencimento": "2026-06-01",
                "data_pagamento": timezone.localdate().isoformat(),
                "status": "pendente",
                "lembrete_em": "",
                "observacoes": "",
            },
        )

        parcela.refresh_from_db()
        venda.refresh_from_db()
        evento.refresh_from_db()
        self.assertRedirects(response, reverse("financeiro"))
        self.assertEqual(parcela.status, "pendente")
        self.assertEqual(parcela.valor_recebido, Decimal("0.00"))
        self.assertIsNone(parcela.data_pagamento)
        self.assertEqual(venda.status, "pendente")
        self.assertFalse(evento.pagamento_recebido)

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
        Parcela.objects.create(venda=venda, numero=1, valor="400.00", vencimento="2030-07-03", status="pendente")
        Parcela.objects.create(venda=venda, numero=2, valor="200.00", vencimento="2030-08-03", status="pendente")
        Parcela.objects.create(venda=venda, numero=3, valor="200.00", vencimento="2030-09-03", status="pendente")

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

    def test_painel_relatorios_filtra_periodo_unico(self):
        cliente = Cliente.objects.create(nome="Cliente Periodo")
        venda_julho = Venda.objects.create(
            cliente=cliente,
            titulo="Venda Julho",
            data_venda="2026-07-10",
            valor_total="500.00",
            status="pendente",
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda_julho,
            nome="Evento Julho",
            tipo_evento="aniversario",
            valor_cobrado="500.00",
        )
        Parcela.objects.create(
            venda=venda_julho,
            numero=1,
            valor="500.00",
            valor_recebido="500.00",
            vencimento="2026-07-10",
            data_pagamento="2026-07-11",
            status="pago",
        )
        Despesa.objects.create(descricao="Despesa Julho", categoria="Fixo", valor="150.00", data="2026-07-12")
        venda_agosto = Venda.objects.create(
            cliente=cliente,
            titulo="Venda Agosto",
            data_venda="2026-08-10",
            valor_total="700.00",
            status="pendente",
        )
        Evento.objects.create(
            cliente=cliente,
            venda=venda_agosto,
            nome="Evento Agosto",
            tipo_evento="aniversario",
            valor_cobrado="700.00",
        )
        Parcela.objects.create(
            venda=venda_agosto,
            numero=1,
            valor="700.00",
            valor_recebido="700.00",
            vencimento="2026-08-10",
            data_pagamento="2026-08-11",
            status="pago",
        )

        response = self.client.get(reverse("relatorios"), {"inicio": "2026-07-01", "fim": "2026-07-31"})

        self.assertEqual(response.context["receita_mes"], Decimal("500.00"))
        self.assertEqual(response.context["despesa_mes"], Decimal("150.00"))
        self.assertContains(response, 'name="inicio" value="2026-07-01"')
        self.assertContains(response, 'name="fim" value="2026-07-31"')
        self.assertContains(response, "/relatorios/receitas/pdf/?inicio=2026-07-01&fim=2026-07-31")
        self.assertContains(response, "Venda Julho")
        self.assertNotContains(response, "Venda Agosto")
