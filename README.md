# README - Instalacao do CRM Fotografos no PC do cliente

Este projeto e um sistema local em Django para organizar clientes, vendas, financeiro, agenda, contratos, documentos e oportunidades de uma empresa de fotografia.

O cliente usa o sistema pelo navegador, como se fosse um programa instalado no computador.

## 1. O que o cliente precisa ter instalado

O cliente nao precisa instalar VS Code.

Ele so precisa ter:

- Windows
- Python 3 instalado
- Navegador, como Chrome, Edge ou Firefox

Durante a instalacao do Python, marque a opcao:

```text
Add python.exe to PATH
```

Isso e muito importante. Se essa opcao nao for marcada, os arquivos `.bat` podem nao conseguir encontrar o Python.

## 2. Baixar ou copiar o projeto

Copie a pasta completa do projeto para o computador do cliente.

Recomendacao:

```text
C:\CRM_Fotografos
```

Evite deixar em Downloads, Area de Trabalho ou pasta temporaria.

A pasta deve conter arquivos como:

```text
manage.py
requirements.txt
db.sqlite3
instalar_cliente_windows.bat
criar_atalhos_windows.bat
iniciar_crm.bat
iniciar_crm_oculto.vbs
backup_crm.bat
backup_crm_silencioso.bat
configurar_backup_automatico.bat
```

## 3. Primeira instalacao

Entre na pasta do projeto:

```text
C:\CRM_Fotografos
```

Clique duas vezes em:

```text
instalar_cliente_windows.bat
```

Esse arquivo vai:

- Criar o ambiente Python local `.venv`
- Instalar o Django
- Instalar as dependencias do projeto
- Aplicar as migrations
- Preparar o banco `db.sqlite3`
- Perguntar se voce quer criar o usuario administrador

Quando aparecer a criacao do admin, preencha:

```text
Username: admin
Email address: pode deixar vazio ou colocar o e-mail do cliente
Password: crie uma senha
Password again: repita a senha
```

Importante: guarde essa senha.

Se o banco `db.sqlite3` ja vier pronto com usuario criado, voce pode responder `N` quando o instalador perguntar se deseja criar o admin.

## 4. Criar atalho na Area de Trabalho

Depois da instalacao, clique duas vezes em:

```text
criar_atalhos_windows.bat
```

Esse arquivo vai criar um atalho chamado:

```text
CRM Fotografos
```

na Area de Trabalho.

Ele tambem vai perguntar se voce quer abrir o sistema automaticamente quando o Windows ligar.

Recomendacao:

```text
S
```

Assim, quando o cliente ligar o computador, o CRM ja inicia.

## 5. Configurar backup automatico

O arquivo `criar_atalhos_windows.bat` tambem pergunta se voce quer configurar backup automatico diario.

Recomendacao:

```text
S
```

O backup sera feito todos os dias as:

```text
18:00
```

Os backups ficam em:

```text
Documentos\Backups_CRM_Fotografos
```

Exemplo:

```text
C:\Users\NOME_DO_CLIENTE\Documents\Backups_CRM_Fotografos
```

Cada backup fica em uma pasta com data e hora, tipo:

```text
Backup_CRM_2026-06-01_18-00-00
```

Se a criacao do backup automatico der erro, execute o arquivo abaixo como administrador:

```text
configurar_backup_automatico.bat
```

## 6. Como o cliente vai usar no dia a dia

O cliente so precisa clicar no atalho:

```text
CRM Fotografos
```

na Area de Trabalho.

O sistema vai abrir no navegador em:

```text
http://127.0.0.1:8000/
```

Se pedir login, use o usuario admin criado na instalacao.

## 7. Como iniciar manualmente

Se o atalho nao abrir ou se voce quiser testar direto pela pasta do projeto, clique duas vezes em:

```text
iniciar_crm.bat
```

Esse arquivo abre o navegador e inicia o servidor local do Django.

## 8. Como fazer backup manual

Se quiser fazer backup manual a qualquer momento, entre na pasta do projeto e clique duas vezes em:

```text
backup_crm.bat
```

Ele copia:

```text
db.sqlite3
media\
```

para:

```text
Documentos\Backups_CRM_Fotografos
```

## 9. O que precisa ser salvo no backup

O banco principal e:

```text
db.sqlite3
```

Nele ficam:

- Clientes
- Eventos
- Parcelas
- Usuarios
- Senhas
- Dados financeiros
- Informacoes cadastradas pelo sistema

A pasta de arquivos e:

```text
media\
```

Nela ficam anexos, PDFs, contratos assinados e arquivos enviados, caso o sistema use isso.

Entao o backup importante e sempre:

```text
db.sqlite3
media\
```

## 10. Cuidados importantes

Nao apagar estes arquivos e pastas:

```text
db.sqlite3
media\
.venv\
manage.py
crm\
crm_fotografos\
templates\
static\
```

Nao mover a pasta do sistema depois de criar os atalhos.

Se precisar mover, crie os atalhos novamente usando:

```text
criar_atalhos_windows.bat
```

## 11. Se o sistema nao abrir

Entre na pasta do projeto e clique em:

```text
iniciar_crm.bat
```

Se aparecer erro, verifique:

- Python instalado corretamente
- A pasta `.venv` existe
- O arquivo `db.sqlite3` existe
- A porta `8000` nao esta sendo usada por outro programa

Se a porta estiver ocupada, feche outros terminais ou reinicie o computador.

## 12. Como restaurar um backup

1. Feche o sistema.
2. Va ate a pasta de backups:

```text
Documentos\Backups_CRM_Fotografos
```

3. Escolha a pasta do backup desejado.
4. Copie o arquivo:

```text
db.sqlite3
```

5. Cole dentro da pasta principal do sistema:

```text
C:\CRM_Fotografos
```

6. Se existir pasta `media` no backup, copie ela tambem para:

```text
C:\CRM_Fotografos
```

7. Abra o sistema novamente pelo atalho.

## 13. Fluxo resumido para instalacao

No PC do cliente:

1. Instalar Python 3 com `Add python.exe to PATH`
2. Copiar projeto para `C:\CRM_Fotografos`
3. Rodar `instalar_cliente_windows.bat`
4. Criar usuario admin, se necessario
5. Rodar `criar_atalhos_windows.bat`
6. Aceitar abrir com Windows
7. Aceitar backup automatico
8. Abrir `CRM Fotografos` pela Area de Trabalho

Pronto. O cliente usa como um programa normal, clicando no atalho.

## 14. Acesso ao sistema

Com o servidor rodando, abra:

```text
http://127.0.0.1:8000/
```

Admin do banco:

```text
http://127.0.0.1:8000/admin/
```

## 15. Menu do CRM

### Painel

Mostra a visao geral do negocio: receitas, despesas, saldo, contratos, trabalhos do mes, tarefas, oportunidades, documentos pendentes e alertas.

### Financeiro

Controla vendas, pagamentos, parcelas, vencimentos, cobrancas e status de cada cliente.

### Despesas

Registra custos da empresa, como estudio, software, anuncios, impressao, equipamentos e servicos.

### Pipeline

Acompanha leads e oportunidades nas etapas de novo lead, orcamento, negociacao, fechado e perdido.

### Agenda

Centraliza compromissos, ensaios, reunioes, entregas, tarefas e pagamentos a receber.

### Clientes

Cadastro principal dos contatos, com telefone, e-mail, origem, tipo de evento, data do evento e proxima oportunidade.

### Documentos

Acompanha contratos, autorizacoes, documentos enviados, documentos pendentes e PDFs.

### Alertas

Mostra parcelas vencidas, cobrancas ativas e oportunidades comerciais proximas.

### Banco/Admin

Painel administrativo nativo do Django para editar registros diretamente no banco.

## 16. Envio de documentos por WhatsApp e e-mail

A tela de documentos pode enviar mensagens, mas precisa de credenciais externas configuradas.

Para WhatsApp Cloud API / Meta, edite o arquivo `.env`:

```text
WHATSAPP_PHONE_NUMBER_ID=SEU_PHONE_NUMBER_ID
WHATSAPP_ACCESS_TOKEN=SEU_TOKEN_DE_ACESSO
WHATSAPP_API_VERSION=v20.0
```

Para e-mail SMTP, edite o arquivo `.env`:

```text
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_HOST_USER=seuemail@gmail.com
EMAIL_HOST_PASSWORD=sua_senha_de_app
DEFAULT_FROM_EMAIL=seuemail@gmail.com
```

Depois de alterar o `.env`, reinicie o sistema pelo atalho.

Enquanto a API do WhatsApp nao estiver configurada, use o botao de abrir WhatsApp Web dentro do sistema e envie manualmente.

