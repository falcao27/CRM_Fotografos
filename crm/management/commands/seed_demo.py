from datetime import time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from crm.models import Cliente, Despesa, Documento, Oportunidade, Parcela, Tarefa, Venda
from crm.views import gerar_parcelas


class Command(BaseCommand):
    help = "Cria dados ficticios para testar e visualizar o CRM."

    def handle(self, *args, **options):
        hoje = timezone.localdate()

        clientes_data = [
            {
                "nome": "Juliana Freitas",
                "telefone": "(85) 98888-1001",
                "email": "juliana@email.com",
                "origem": "Instagram",
                "tipo_evento": "Casamento",
                "data_evento": hoje + timedelta(days=42),
                "proxima_oportunidade": hoje + timedelta(days=312),
            },
            {
                "nome": "Camila Rocha",
                "telefone": "(85) 98888-1002",
                "email": "camila@email.com",
                "origem": "Indicacao",
                "tipo_evento": "Ensaio gestante",
                "data_evento": hoje + timedelta(days=9),
                "proxima_oportunidade": hoje + timedelta(days=302),
            },
            {
                "nome": "Ricardo Mendes",
                "telefone": "(85) 98888-1003",
                "email": "ricardo@email.com",
                "origem": "Google",
                "tipo_evento": "Aniversario infantil",
                "data_evento": hoje + timedelta(days=18),
                "proxima_oportunidade": hoje + timedelta(days=420),
            },
            {
                "nome": "Ana Costa",
                "telefone": "(85) 98888-1004",
                "email": "ana@email.com",
                "origem": "Feira de noivas",
                "tipo_evento": "Casamento",
                "data_evento": hoje + timedelta(days=73),
                "proxima_oportunidade": hoje + timedelta(days=305),
            },
            {
                "nome": "Fernando Lima",
                "telefone": "(85) 98888-1005",
                "email": "fernando@email.com",
                "origem": "WhatsApp",
                "tipo_evento": "Ensaio externo",
                "data_evento": hoje + timedelta(days=25),
                "proxima_oportunidade": hoje + timedelta(days=365),
            },
            {
                "nome": "Familia Costa",
                "telefone": "(85) 98888-1006",
                "email": "familia.costa@email.com",
                "origem": "Cliente antigo",
                "tipo_evento": "Ensaio familia",
                "data_evento": hoje + timedelta(days=6),
                "proxima_oportunidade": hoje + timedelta(days=300),
            },
        ]

        clientes = {}
        for dados in clientes_data:
            cliente, _ = Cliente.objects.update_or_create(
                email=dados["email"],
                defaults={**dados, "observacoes": "Cliente ficticio para demonstracao do CRM."},
            )
            clientes[cliente.nome] = cliente

        vendas_data = [
            ("Casamento Juliana e Pedro", "Juliana Freitas", Decimal("4800.00"), "parcelado", 4, "cartao", "pendente", hoje - timedelta(days=14)),
            ("Ensaio gestante Camila", "Camila Rocha", Decimal("1200.00"), "avista", 1, "pix", "pago", hoje - timedelta(days=7)),
            ("Aniversario do Theo", "Ricardo Mendes", Decimal("2500.00"), "parcelado", 5, "boleto", "pendente", hoje - timedelta(days=20)),
            ("Pre-wedding Ana e Lucas", "Ana Costa", Decimal("6800.00"), "parcelado", 6, "pix", "pendente", hoje - timedelta(days=3)),
            ("Ensaio externo Fernando", "Fernando Lima", Decimal("1500.00"), "parcelado", 3, "dinheiro", "pendente", hoje - timedelta(days=10)),
        ]

        for titulo, cliente_nome, valor, condicao, parcelas, forma, status, data_venda in vendas_data:
            venda, created = Venda.objects.update_or_create(
                titulo=titulo,
                cliente=clientes[cliente_nome],
                defaults={
                    "data_venda": data_venda,
                    "valor_total": valor,
                    "status": status,
                    "forma_pagamento": forma,
                    "condicao_pagamento": condicao,
                    "quantidade_parcelas": parcelas,
                    "observacoes": "Venda ficticia criada para testar o painel financeiro.",
                },
            )
            if created or not venda.parcelas.exists():
                gerar_parcelas(venda, hoje - timedelta(days=5))

        Parcela.objects.filter(venda__titulo="Ensaio gestante Camila").update(
            status="pago",
            data_pagamento=hoje - timedelta(days=2),
        )
        Parcela.objects.filter(venda__titulo="Casamento Juliana e Pedro", numero=1).update(
            status="pago",
            data_pagamento=hoje - timedelta(days=4),
        )
        Parcela.objects.filter(venda__titulo="Aniversario do Theo", numero=1).update(
            vencimento=hoje - timedelta(days=2),
            lembrete_em=hoje - timedelta(days=5),
        )

        despesas_data = [
            ("Aluguel de estudio", "Estrutura", Decimal("850.00"), "pago", "pix", hoje - timedelta(days=5)),
            ("Adobe Lightroom", "Software", Decimal("89.90"), "pago", "cartao", hoje - timedelta(days=8)),
            ("Anuncios Instagram", "Marketing", Decimal("420.00"), "pendente", "cartao", hoje + timedelta(days=4)),
            ("Segundo fotografo", "Equipe", Decimal("700.00"), "pendente", "pix", hoje + timedelta(days=10)),
            ("Impressao de album", "Produto", Decimal("1150.00"), "atrasado", "boleto", hoje - timedelta(days=3)),
        ]
        for descricao, categoria, valor, status, forma, data in despesas_data:
            Despesa.objects.update_or_create(
                descricao=descricao,
                defaults={
                    "categoria": categoria,
                    "valor": valor,
                    "status": status,
                    "forma_pagamento": forma,
                    "data": data,
                    "vencimento": data if status != "pago" else None,
                    "observacoes": "Despesa ficticia para demonstracao.",
                },
            )

        oportunidades_data = [
            ("Mariana Silva", "Ensaio externo", Decimal("1500.00"), "novo", "Instagram", hoje + timedelta(days=1)),
            ("Carlos Monteiro", "Aniversario 1 ano", Decimal("900.00"), "novo", "WhatsApp", hoje + timedelta(days=2)),
            ("Ana Costa", "Pacote casamento completo", Decimal("6800.00"), "orcamento", "Feira de noivas", hoje + timedelta(days=3)),
            ("Fernanda Prado", "Ensaio gestante", Decimal("2200.00"), "negociacao", "Indicacao", hoje + timedelta(days=5)),
            ("Juliana Freitas", "Casamento", Decimal("4800.00"), "fechado", "Instagram", hoje + timedelta(days=7)),
        ]
        for nome, titulo, valor, etapa, origem, contato in oportunidades_data:
            Oportunidade.objects.update_or_create(
                nome_lead=nome,
                titulo=titulo,
                defaults={
                    "cliente": clientes.get(nome),
                    "tipo_evento": titulo,
                    "valor_estimado": valor,
                    "etapa": etapa,
                    "origem": origem,
                    "proximo_contato": contato,
                    "observacoes": "Lead ficticio para testar o pipeline.",
                },
            )

        tarefas_data = [
            ("Ensaio Gestante Camila", "trabalho", "Camila Rocha", hoje, time(9, 0), "pendente"),
            ("Entrega de fotos", "entrega", "Familia Costa", hoje, time(14, 0), "pendente"),
            ("Reuniao orcamento", "reuniao", "Ricardo Mendes", hoje + timedelta(days=1), time(16, 30), "pendente"),
            ("Editar fotos casamento", "tarefa", "Juliana Freitas", hoje + timedelta(days=2), time(10, 0), "pendente"),
            ("Backup do HD externo", "tarefa", None, hoje - timedelta(days=1), time(18, 0), "atrasada"),
            ("Album de formatura", "tarefa", "Fernando Lima", hoje - timedelta(days=3), time(15, 0), "concluida"),
        ]
        for titulo, tipo, cliente_nome, data, hora, status in tarefas_data:
            Tarefa.objects.update_or_create(
                titulo=titulo,
                defaults={
                    "tipo": tipo,
                    "cliente": clientes.get(cliente_nome) if cliente_nome else None,
                    "data": data,
                    "hora": hora,
                    "status": status,
                    "descricao": "Tarefa ficticia para demonstracao da agenda.",
                },
            )

        documentos_data = [
            ("Contrato casamento Juliana e Pedro", "Juliana Freitas", "pendente", hoje + timedelta(days=3)),
            ("Autorizacao de uso de imagem - Camila", "Camila Rocha", "assinado", hoje - timedelta(days=1)),
            ("Contrato aniversario Theo", "Ricardo Mendes", "vencido", hoje - timedelta(days=2)),
            ("Contrato pre-wedding Ana e Lucas", "Ana Costa", "pendente", hoje + timedelta(days=8)),
        ]
        for titulo, cliente_nome, status, limite in documentos_data:
            cliente = clientes[cliente_nome]
            Documento.objects.update_or_create(
                titulo=titulo,
                defaults={
                    "cliente": cliente,
                    "status": status,
                    "contato_whatsapp": cliente.telefone,
                    "contato_email": cliente.email,
                    "forma_envio": "ambos",
                    "enviado_em": hoje - timedelta(days=1) if status in ["assinado", "pendente", "vencido"] else None,
                    "assinado_em": hoje - timedelta(days=1) if status == "assinado" else None,
                    "data_limite": limite,
                    "conteudo_contrato": (
                        "CONTRATO DE PRESTACAO DE SERVICOS FOTOGRAFICOS\n\n"
                        f"Cliente: {cliente.nome}\n"
                        f"Contato: {cliente.telefone} - {cliente.email}\n"
                        f"Servico contratado: {cliente.tipo_evento}\n"
                        "Valor: conforme proposta aprovada no CRM.\n"
                        f"Data do evento: {cliente.data_evento.strftime('%d/%m/%Y') if cliente.data_evento else 'a definir'}\n\n"
                        "O documento deve ser enviado virtualmente e o status so deve ser alterado "
                        "para assinado quando o contrato retornar assinado pelo cliente.\n\n"
                        "Assinatura do cliente: ______________________________\n"
                        "Assinatura do fotografo: ____________________________"
                    ),
                    "observacoes": "Documento ficticio para acompanhar assinatura.",
                },
            )

        self.stdout.write(self.style.SUCCESS("Dados ficticios criados com sucesso."))
