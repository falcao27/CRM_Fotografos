# CRM Fotografos

Sistema local em Django para organizar clientes, vendas, financeiro, agenda e oportunidades de uma empresa de fotografia.

## Como acessar

Com o servidor rodando, abra:

```text
http://127.0.0.1:8000/
```

Admin do banco:

```text
http://127.0.0.1:8000/admin/
usuario: admin
senha: admin123
```

## Como rodar

```powershell
cd C:\Users\Usuario\Downloads\CRM_Fotografos
..\project_fotografia\.venv\Scripts\python manage.py runserver
```

Se precisar instalar do zero:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Dados ficticios

Para criar dados de teste e visualizar o sistema preenchido:

```powershell
..\project_fotografia\.venv\Scripts\python manage.py seed_demo
```

Esse comando cria clientes, vendas, parcelas, despesas, oportunidades, tarefas e documentos ficticios. Ele pode ser executado novamente; os principais registros sao atualizados em vez de duplicados.

## Menu e paineis

### Painel

E a visao geral do negocio.

Mostra:

- Receitas recebidas no mes.
- Receitas a receber.
- Despesas pagas.
- Despesas a pagar.
- Saldo atual e saldo previsto.
- Contratos criados no mes.
- Trabalhos do mes.
- Tarefas pendentes e atrasadas.
- Oportunidades abertas.
- Documentos pendentes.
- Grafico simples de receitas vs despesas.
- Agenda da semana.
- Progresso das tarefas do mes.
- Alertas de cobranca.
- Alertas comerciais 10 meses antes da proxima oportunidade.

Use esse painel para saber rapidamente se o mes esta saudavel.

### Financeiro

E o controle de vendas e pagamentos dos clientes.

A tela principal mostra apenas um card com o nome de cada cliente para nao ficar poluida quando houver muitos contatos. Ao clicar no cliente, abre um painel lateral com:

- Vendas desse cliente.
- Forma de pagamento: pix, dinheiro, boleto, cartao, transferencia ou outro.
- Condicao: a vista ou parcelado.
- Parcelas.
- Vencimento de cada parcela.
- Lembrete de cobranca.
- Status da parcela: pendente, pago ou atrasado.
- Botoes para editar venda, excluir venda e editar parcela.

Quando uma venda parcelada e cadastrada, o sistema cria as parcelas automaticamente.

Se uma parcela estiver pendente e a data de vencimento ja passou, o painel mostra o status como `Vencido` e exibe um alerta no card do cliente. Isso ajuda a identificar rapidamente quem precisa ser cobrado.

### Despesas

Serve para registrar os custos da empresa.

Exemplos:

- Aluguel de estudio.
- Software.
- Anuncios.
- Segundo fotografo.
- Impressao de album.
- Equipamentos.

Cada despesa tem:

- Descricao.
- Categoria.
- Valor.
- Data.
- Vencimento.
- Status.
- Forma de pagamento.
- Observacoes.

Esses dados entram no balanco do dashboard.

### Pipeline

E o quadro de vendas para acompanhar leads e oportunidades.

Etapas:

- Novo lead.
- Orcamento.
- Negociacao.
- Fechado.
- Perdido.

Cada oportunidade tem:

- Nome do lead.
- Cliente vinculado, se ja existir.
- Tipo de evento.
- Valor estimado.
- Prioridade.
- Origem do lead.
- Data do proximo contato.
- Observacoes.

Use esse painel para nao esquecer leads que chamaram no Instagram, WhatsApp ou por indicacao.

Quando uma oportunidade e marcada como `Fechado`, o CRM cria ou vincula o cliente automaticamente e abre a tela de cadastro desse cliente. O admin deve conferir telefone, e-mail, tipo de evento e observacoes antes de seguir para contrato, agenda ou financeiro.

### Agenda

Centraliza compromissos, trabalhos, tarefas e pagamentos.

Pode registrar:

- Ensaios.
- Reunioes.
- Entregas.
- Edicoes.
- Lembretes.
- Tarefas internas.

Tambem mostra pagamentos a receber vindos das parcelas pendentes.

Na area `Pagamentos a receber`, a agenda mostra apenas o nome do cliente e o total em aberto. Ao clicar no cliente, aparecem as parcelas, valores e datas de vencimento.

Cada tarefa tem:

- Cliente vinculado.
- Titulo.
- Tipo.
- Data.
- Hora.
- Status.
- Descricao.

### Clientes

E o cadastro principal de contatos.

Cada cliente pode ter:

- Nome.
- Telefone.
- E-mail.
- Origem.
- Tipo de evento.
- Data do evento.
- Proxima oportunidade.
- Observacoes.

O campo "proxima oportunidade" alimenta o alerta comercial. O sistema considera 10 meses antes dessa data como inicio da janela para tentar vender novamente.

### Documentos

Serve para acompanhar contratos, autorizacoes e documentos pendentes.

Cada documento tem:

- Cliente.
- Titulo.
- Contato de WhatsApp.
- Contato de e-mail.
- Forma de envio: WhatsApp, e-mail ou ambos.
- Data de envio.
- Modelo/conteudo do contrato para editar.
- Status: rascunho, enviado, pendente, assinado ou vencido.
- Data limite.
- Observacoes.

O contrato e pensado para envio virtual. O status so deve ser alterado para `Assinado` quando o documento retornar assinado e o admin confirmar manualmente no cadastro.

O contrato tambem pode ser aberto ou baixado como PDF editavel. O PDF e gerado a partir do campo `conteudo do contrato`, entao o admin edita o texto no cadastro do documento e depois usa os botoes `Abrir PDF` ou `Baixar PDF`.

#### Envio real de documentos

A tela de documentos tem um botao de envio. Ele faz envio real, mas precisa de credenciais externas configuradas no ambiente.

Para envio por WhatsApp, configure a API do WhatsApp Cloud/Meta:

```powershell
copy .env.example .env
```

Depois edite o arquivo `.env` e preencha:

```text
WHATSAPP_PHONE_NUMBER_ID=SEU_PHONE_NUMBER_ID
WHATSAPP_ACCESS_TOKEN=SEU_TOKEN_DE_ACESSO
WHATSAPP_API_VERSION=v20.0
```

O telefone do cliente deve estar com DDD. Se nao comecar com `55`, o sistema adiciona o codigo do Brasil automaticamente.

Para envio por e-mail, configure SMTP:

```text
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_HOST_USER=seuemail@gmail.com
EMAIL_HOST_PASSWORD=sua_senha_de_app
DEFAULT_FROM_EMAIL=seuemail@gmail.com
```

Depois de configurar as variaveis, reinicie o servidor:

```powershell
..\project_fotografia\.venv\Scripts\python manage.py runserver
```

Se o envio por e-mail for usado, o PDF editavel vai anexado automaticamente. Se o envio falhar, o CRM mostra a mensagem de erro na tela e grava o retorno no documento. O status so muda para `Enviado para assinatura` quando o provedor confirma o envio.

Enquanto a API do WhatsApp nao estiver configurada, use o botao `Abrir WhatsApp` no painel de documentos. Ele abre o WhatsApp Web com a conversa e o texto do contrato preenchidos; nesse modo, o envio acontece quando o admin clica em enviar dentro do WhatsApp.

No WhatsApp Web o navegador nao permite anexar arquivos automaticamente. Por isso, o CRM abre uma tela com dois passos: baixar o PDF editavel e abrir a conversa do cliente. O admin deve anexar o PDF manualmente no WhatsApp Web.

Com a WhatsApp Cloud API configurada, o botao `Enviar` envia o PDF automaticamente como documento/anexo, sem depender do WhatsApp Web.

### Alertas

Reune o que precisa de atencao.

Mostra:

- Parcelas vencidas.
- Parcelas com lembrete de cobranca ativo.
- Clientes dentro da janela de 10 meses antes da proxima oportunidade.

### Banco/Admin

E o painel administrativo nativo do Django.

Use quando precisar mexer diretamente nos registros do banco com mais liberdade. Ele permite incluir, editar e excluir:

- Clientes.
- Vendas.
- Parcelas.
- Despesas.
- Oportunidades.
- Tarefas.
- Documentos.
- Usuarios do sistema.

## Fluxo recomendado de uso

1. Cadastre o cliente em `Clientes`.
2. Cadastre a venda em `Financeiro`.
3. Se a venda for parcelada, confira as parcelas geradas.
4. Cadastre custos em `Despesas`.
5. Coloque leads em `Pipeline`.
6. Registre ensaios, reunioes e entregas em `Agenda`.
7. Acompanhe contratos em `Documentos`.
8. Abra o `Painel` diariamente para ver saude financeira e pendencias.
9. Use `Alertas` para cobrar clientes e reativar oportunidades.

## Observacao

Este projeto esta em modo local/desenvolvimento. Antes de usar em producao, altere a senha do admin e configure uma chave secreta segura.
