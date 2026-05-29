import json
import re
import uuid
from urllib.parse import quote
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import EmailMessage

from .pdf import gerar_pdf_documento, nome_pdf_documento


class EnvioDocumentoError(Exception):
    pass


GOVBR_ASSINADOR_URL = "https://www.gov.br/pt-br/servicos/assinatura-eletronica"


def normalizar_whatsapp(numero):
    digitos = re.sub(r"\D", "", numero or "")
    if not digitos:
        return ""
    if digitos.startswith("55"):
        return digitos
    return "55" + digitos


def enviar_documento_email(documento):
    if not documento.contato_email:
        raise EnvioDocumentoError("Documento sem e-mail do cliente.")
    if not settings.EMAIL_HOST_USER and settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"):
        raise EnvioDocumentoError("SMTP nao configurado. Defina EMAIL_HOST_USER e EMAIL_HOST_PASSWORD.")

    mensagem = (
        f"Ola, {documento.cliente.nome if documento.cliente else ''}.\n\n"
        "Segue o contrato em PDF para conferencia.\n\n"
        "Para assinar digitalmente pelo gov.br:\n"
        f"1. Acesse {GOVBR_ASSINADOR_URL}\n"
        "2. Entre com sua conta gov.br prata ou ouro.\n"
        "3. Envie o PDF anexado, assine e baixe o arquivo assinado.\n"
        "4. Responda este e-mail com o PDF assinado para anexarmos ao cadastro do evento.\n\n"
        "Obrigado."
    )
    email = EmailMessage(
        subject=documento.titulo,
        body=mensagem,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[documento.contato_email],
    )
    email.attach(nome_pdf_documento(documento), gerar_pdf_documento(documento), "application/pdf")
    enviados = email.send(fail_silently=False)
    if enviados != 1:
        raise EnvioDocumentoError("O servidor de e-mail nao confirmou o envio.")
    return "E-mail enviado com PDF anexado com sucesso."


def enviar_documento_whatsapp(documento):
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    api_version = getattr(settings, "WHATSAPP_API_VERSION", "v20.0")

    if not token or not phone_number_id:
        raise EnvioDocumentoError(
            "WhatsApp nao configurado. Defina WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID."
        )

    numero = normalizar_whatsapp(documento.contato_whatsapp)
    if not numero:
        raise EnvioDocumentoError("Documento sem WhatsApp do cliente.")

    media_id = enviar_pdf_para_whatsapp(documento, token, phone_number_id, api_version)
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": nome_pdf_documento(documento),
            "caption": (
                f"Ola, {documento.cliente.nome if documento.cliente else ''}. "
                "Segue o contrato em PDF. Assine pelo gov.br e envie o PDF assinado de volta."
            ),
        },
    }
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        erro = exc.read().decode("utf-8", errors="replace")
        raise EnvioDocumentoError(f"WhatsApp recusou o envio: {erro}") from exc
    except urllib.error.URLError as exc:
        raise EnvioDocumentoError(f"Falha de conexao com WhatsApp: {exc.reason}") from exc

    return f"WhatsApp enviado com sucesso. Retorno: {body}"


def whatsapp_api_configurado():
    return bool(
        getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
        and getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    )


def enviar_pdf_para_whatsapp(documento, token, phone_number_id, api_version):
    boundary = f"----crm-fotografos-{uuid.uuid4().hex}"
    filename = nome_pdf_documento(documento)
    pdf = gerar_pdf_documento(documento)
    partes = []

    def campo(nome, valor):
        partes.append(f"--{boundary}\r\n".encode())
        partes.append(f'Content-Disposition: form-data; name="{nome}"\r\n\r\n'.encode())
        partes.append(str(valor).encode())
        partes.append(b"\r\n")

    campo("messaging_product", "whatsapp")
    campo("type", "application/pdf")
    partes.append(f"--{boundary}\r\n".encode())
    partes.append(
        (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
    )
    partes.append(pdf)
    partes.append(b"\r\n")
    partes.append(f"--{boundary}--\r\n".encode())
    body = b"".join(partes)

    request = urllib.request.Request(
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/media",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            retorno = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        erro = exc.read().decode("utf-8", errors="replace")
        raise EnvioDocumentoError(f"WhatsApp recusou o upload do PDF: {erro}") from exc
    except urllib.error.URLError as exc:
        raise EnvioDocumentoError(f"Falha de conexao ao enviar PDF para WhatsApp: {exc.reason}") from exc

    media_id = retorno.get("id")
    if not media_id:
        raise EnvioDocumentoError(f"WhatsApp nao retornou o ID do PDF enviado: {retorno}")
    return media_id


def enviar_documento(documento):
    resultados = []
    deve_enviar_email = documento.forma_envio in ["email", "ambos"]
    whatsapp_sem_api = documento.forma_envio in ["whatsapp", "ambos"] and not whatsapp_api_configurado()
    if documento.forma_envio == "whatsapp" and whatsapp_sem_api and documento.contato_email:
        deve_enviar_email = True

    if deve_enviar_email:
        resultados.append(enviar_documento_email(documento))
    if whatsapp_sem_api:
        if not documento.contato_email:
            raise EnvioDocumentoError(
                "WhatsApp automatico nao configurado e o documento esta sem e-mail do cliente. "
                "Edite o documento ou o cliente e informe o e-mail para enviar o PDF."
            )
        resultados.append("Aviso de WhatsApp pendente: use o botao de WhatsApp manual para abrir a mensagem pronta.")
    elif documento.forma_envio in ["whatsapp", "ambos"]:
        resultados.append(enviar_documento_whatsapp(documento))
    return "\n".join(resultados)


def mensagem_documento_whatsapp(documento):
    return (
        f"Ola, {documento.cliente.nome if documento.cliente else ''}.\n\n"
        "Te enviei o contrato no e-mail com o PDF anexado.\n\n"
        "Para assinar digitalmente, acesse o Assinador gov.br:\n"
        f"{GOVBR_ASSINADOR_URL}\n\n"
        "Depois de assinar, responda o e-mail ou me envie o PDF assinado por aqui."
    )


def link_whatsapp_manual(documento):
    numero = normalizar_whatsapp(documento.contato_whatsapp)
    if not numero:
        raise EnvioDocumentoError("Documento sem WhatsApp do cliente.")
    return f"https://wa.me/{numero}?text={quote(mensagem_documento_whatsapp(documento))}"
