import struct
import zlib
from decimal import Decimal
from pathlib import Path
from textwrap import wrap

from django.conf import settings
from django.utils import timezone


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LOGO_PATH = Path(settings.BASE_DIR) / "static" / "crm" / "brand" / "joao_bosco_logo_contract.png"


def pdf_escape(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "")
    )


def brl(valor):
    if valor in [None, ""]:
        return ""
    valor = Decimal(valor)
    return f"{valor:.2f}".replace(".", ",")


def data_br(data):
    return data.strftime("%d/%m/%Y") if data else ""


def paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def carregar_png_rgb(path):
    if not path.exists():
        return None

    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None

    pos = 8
    width = height = color_type = bit_depth = None
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if bit_depth != 8 or color_type not in {2, 6} or not width or not height:
        return None

    channels = 4 if color_type == 6 else 3
    bpp = channels
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    offset = 0
    previous = bytearray(stride)
    rgb = bytearray(width * height * 3)
    rgb_offset = 0

    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        scanline = bytearray(raw[offset : offset + stride])
        offset += stride
        reconstructed = bytearray(stride)

        for i, value in enumerate(scanline):
            left = reconstructed[i - bpp] if i >= bpp else 0
            up = previous[i]
            upper_left = previous[i - bpp] if i >= bpp else 0
            if filter_type == 0:
                reconstructed[i] = value
            elif filter_type == 1:
                reconstructed[i] = (value + left) & 0xFF
            elif filter_type == 2:
                reconstructed[i] = (value + up) & 0xFF
            elif filter_type == 3:
                reconstructed[i] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                reconstructed[i] = (value + paeth(left, up, upper_left)) & 0xFF
            else:
                return None

        for x in range(width):
            px = x * channels
            r, g, b = reconstructed[px], reconstructed[px + 1], reconstructed[px + 2]
            if channels == 4:
                alpha = reconstructed[px + 3]
                r = (r * alpha + 255 * (255 - alpha) + 127) // 255
                g = (g * alpha + 255 * (255 - alpha) + 127) // 255
                b = (b * alpha + 255 * (255 - alpha) + 127) // 255
            rgb[rgb_offset : rgb_offset + 3] = bytes((r, g, b))
            rgb_offset += 3
        previous = reconstructed

    return {
        "width": width,
        "height": height,
        "stream": zlib.compress(bytes(rgb), level=9),
    }


def contexto_contrato(documento):
    cliente = documento.cliente
    evento = documento.evento
    venda = evento.venda if evento and evento.venda_id else None
    parcelas = list(venda.parcelas.all()) if venda else []
    return {
        "cliente": cliente.nome if cliente else "",
        "cpf": "",
        "endereco": "",
        "telefone": documento.contato_whatsapp or (cliente.telefone if cliente else ""),
        "email": documento.contato_email or (cliente.email if cliente else ""),
        "aniversariante": evento.nome if evento else (cliente.nome if cliente else ""),
        "idade": "",
        "local": evento.local_evento if evento else "",
        "data": data_br(evento.data_festa if evento else (cliente.data_evento if cliente else None)),
        "inicio": evento.horario.strftime("%H:%M") if evento and evento.horario else "",
        "fim": "",
        "servico": evento.get_tipo_evento_display() if evento and evento.tipo_evento else (evento.nome if evento else ""),
        "valor": brl(evento.valor_cobrado if evento else ""),
        "forma_pagamento": evento.get_forma_pagamento_display() if evento else "",
        "parcelas": parcelas,
        "data_contrato": timezone.localdate(),
    }


class PdfCanvas:
    def __init__(self, tem_logo=False):
        self.pages = []
        self.commands = []
        self.tem_logo = tem_logo

    def add_page(self):
        if self.commands:
            self.pages.append(self.commands)
        self.commands = []

    def finish(self):
        if self.commands:
            self.pages.append(self.commands)

    def text(self, x, y, value, size=8, font="F1"):
        self.commands.extend(["BT", f"/{font} {size} Tf", f"{x} {y} Td", f"({pdf_escape(value)}) Tj", "ET"])

    def text_rgb(self, x, y, value, size=8, font="F1", rgb=(0, 0, 0)):
        r, g, b = rgb
        self.commands.extend(
            [
                f"{r} {g} {b} rg",
                "BT",
                f"/{font} {size} Tf",
                f"{x} {y} Td",
                f"({pdf_escape(value)}) Tj",
                "ET",
                "0 0 0 rg",
            ]
        )

    def wrapped(self, x, y, value, width=105, size=7.2, line_height=9):
        linhas = []
        for raw in str(value or "").splitlines():
            linhas.extend(wrap(raw, width=width) or [""])
        for linha in linhas:
            self.text(x, y, linha, size=size)
            y -= line_height
        return y

    def line(self, x1, y1, x2, y2, width=0.6):
        self.commands.extend([f"{width} w", f"{x1} {y1} m", f"{x2} {y2} l", "S"])

    def line_rgb(self, x1, y1, x2, y2, width=0.8, rgb=(0, 0, 0)):
        r, g, b = rgb
        self.commands.extend(
            [
                f"{r} {g} {b} RG",
                f"{width} w",
                f"{x1} {y1} m",
                f"{x2} {y2} l",
                "S",
                "0 0 0 RG",
            ]
        )

    def rect(self, x, y, w, h, width=0.6):
        self.commands.extend([f"{width} w", f"{x} {y} {w} {h} re", "S"])

    def image(self, name, x, y, w, h):
        self.commands.append(f"q {w} 0 0 {h} {x} {y} cm /{name} Do Q")


def campo(canvas, label, value, x, y, line_to, size=8):
    canvas.text(x, y, label, size=size, font="F2")
    label_width = len(label) * size * 0.45
    value_x = x + label_width + 3
    if value:
        canvas.text(value_x, y, value, size=size)
    canvas.line(value_x, y - 2, line_to, y - 2)


def campo_fixo(canvas, label, value, label_x, value_x, y, line_to, size=8):
    canvas.text(label_x, y, label, size=size, font="F2")
    if value:
        canvas.text(value_x, y, value, size=size)
    canvas.line(value_x, y - 2, line_to, y - 2)


def desenhar_marca(canvas, x=188, y=796):
    if canvas.tem_logo:
        canvas.image("Logo", 150, 745, 295, 95)
        return
    canvas.line_rgb(x + 4, y + 14, x + 48, y + 10, width=1.2, rgb=(1, 0.47, 0.75))
    canvas.line_rgb(x + 42, y + 10, x + 78, y + 12, width=1.2, rgb=(0.52, 0.84, 0.95))
    canvas.line_rgb(x + 112, y + 20, x + 145, y + 8, width=1.2, rgb=(1, 0.86, 0.2))
    canvas.text_rgb(x + 30, y - 18, "Joao Bosco", size=32, font="F3", rgb=(0.38, 0.38, 0.38))
    canvas.text_rgb(x + 210, y - 34, "FOTOGRAFIA", size=8, font="F2", rgb=(0.96, 0.52, 0.78))


def tabela_servico(canvas, ctx):
    x = 45
    y = 500
    w1 = 392
    w2 = 110
    row_h = 18
    canvas.rect(x, y - (row_h * 8), w1, row_h * 8)
    canvas.rect(x + w1, y - (row_h * 8), w2, row_h * 8)
    for i in range(1, 8):
        canvas.line(x, y - (row_h * i), x + w1 + w2, y - (row_h * i))
    canvas.line(x + w1, y, x + w1, y - (row_h * 8))
    canvas.text(x + 8, y - 15, "Descricao do Servico:", size=8, font="F2")
    canvas.text(x + w1 + 8, y - 15, "Valor", size=8, font="F2")
    canvas.wrapped(x + 8, y - 38, ctx["servico"], width=70, size=7.5)
    canvas.text(x + w1 + 18, y - 38, f"R$ {ctx['valor']}" if ctx["valor"] else "R$", size=8)
    canvas.text(x + 8, y - (row_h * 8) + 8, "TOTAL", size=8, font="F2")
    canvas.text(x + w1 + 18, y - (row_h * 8) + 8, f"R$ {ctx['valor']}" if ctx["valor"] else "R$", size=8, font="F2")
    return y - (row_h * 8) - 24


def parcelas_texto(canvas, ctx, y):
    canvas.text(45, y, f"FORMA DE PAGAMENTO: {ctx['forma_pagamento']}", size=8, font="F2")
    y -= 18
    parcelas = ctx["parcelas"][:6]
    for idx in range(6):
        x = 45 if idx % 2 == 0 else 302
        if idx % 2 == 0 and idx:
            y -= 18
        parcela = parcelas[idx] if idx < len(parcelas) else None
        valor = brl(parcela.valor) if parcela else ""
        data = data_br(parcela.vencimento) if parcela else ""
        texto = f"{idx + 1}a Parcela. Valor {valor or '________'}  Data {data or '____/____/____'}"
        canvas.text(x, y, texto, size=7.2)
    return y - 30


def tabela_adiantamento(canvas, y):
    x = 45
    w1 = 135
    w2 = 185
    w3 = 180
    row_h = 23
    canvas.rect(x, y - row_h * 3, w1 + w2 + w3, row_h * 3)
    canvas.line(x + w1, y, x + w1, y - row_h * 3)
    canvas.line(x + w1 + w2, y, x + w1 + w2, y - row_h * 3)
    canvas.line(x, y - row_h, x + w1 + w2 + w3, y - row_h)
    canvas.line(x, y - row_h * 2, x + w1 + w2 + w3, y - row_h * 2)
    canvas.text(x + w1 + 12, y - 15, "Data", size=8, font="F2")
    canvas.text(x + w1 + w2 + 12, y - 15, "Valor", size=8, font="F2")
    canvas.text(x + 10, y - row_h - 15, "ADIANTAMENTO", size=8, font="F2")
    canvas.text(x + w1 + w2 + 12, y - row_h - 15, "R$", size=8)
    canvas.text(x + 10, y - row_h * 2 - 15, "RESTANTE", size=8, font="F2")
    canvas.text(x + w1 + w2 + 12, y - row_h * 2 - 15, "R$", size=8)
    return y - row_h * 3 - 16


CLAUSULAS_PAGINA_1 = [
    "OBS: PERMANENCIA DE ATE 03HORAS NO EVENTO, INICIANDO A PARTIR DO HORARIO ESTABELECIDO ACIMA.",
    "Sera executado um numero superior aos das fotos acima encomendadas, a fim de aumentar a opcao de escolha.",
    "O CONTRATADO entregara o LINK com todas as fotos do evento para a escolha das imagens que irao para o album no prazo de 20 (vinte) dias uteis apos o evento. O CONTRATANTE tera o prazo de 10 (dez) dias uteis, apos o recebimento das provas, para informar ao CONTRATADO as fotos selecionadas para o album.",
    "O CONTRATANTE tera um prazo de 12 meses, a contar a partir do recebimento das imagens, para informar a selecao de fotos que irao para o album, caso ultrapasse o periodo estipulado, o valor sera reajustado de acordo com nossa tabela atual de precos.",
]

CLAUSULAS_PAGINA_2 = [
    "O CONTRATANTE devera enviar, em documento escrito, para o CONTRATADO, a lista de fotos escolhidas, utilizando a numeracao e nomenclatura original dos arquivos de prova.",
    "O CONTRATADO entregara os trabalhos, apos o evento, de acordo com as datas que seguem: Fotos em LINK 20 (vinte) dias uteis (um LINK com 100 fotos tratadas e outro LINK com todas as imagens em alta resolucao); album 45 (quarenta e cinco) dias uteis apos a devolucao das fotos ou projeto escolhido e aprovado pelo cliente.",
    "Apos a entrega para verificacao e aprovacao do cliente, o mesmo tera 02 (dois) dias uteis para devolucao no caso de necessidade de correcao do PROJETO. Caso nao aconteca a devolucao no prazo estipulado, tera a aprovacao o produto final pelo cliente.",
    "O LINK com fotos em alta resolucao pertencem a empresa, ficando a disposicao para novas reproducoes mediante as remuneracoes estabelecidas entre cliente e empresa.",
    "Os arquivos originais (arquivos de fotos) ficarao na empresa por 30 dias apos finalizar o contrato com contratante.",
    "Em caso de desistencia nao sera devolvido o adiantamento pago.",
    "O Contratante autoriza a utilizacao de sua imagem pelo contratado em seu portfolio, ou em redes social exclusivamente para fins de divulgacao de seu trabalho e sem fins comerciais.",
]


def desenhar_cabecalho(canvas, ctx):
    desenhar_marca(canvas)
    canvas.text(240, 728, "CONTRATO DE SERVICO", size=12, font="F2")
    canvas.text(45, 706, "CONTRATADO:JOAO BOSCO FOTOGRAFIA", size=8, font="F2")
    canvas.text(45, 692, "E-MAIL: JOAOBOSCOFOTOS@GMAIL.COM", size=8, font="F2")
    canvas.text(45, 678, "TEL:(85) 98713-7641", size=8, font="F2")
    canvas.text(45, 664, "CNPJ 25.165.098/0001-68", size=8, font="F2")
    campo_fixo(canvas, "CONTRATANTE:", ctx["cliente"], 45, 125, 640, 345)
    campo_fixo(canvas, "CPF:", ctx["cpf"], 360, 392, 640, 550)
    campo_fixo(canvas, "ENDERECO:", ctx["endereco"], 45, 118, 620, 550)
    canvas.line(45, 603, 550, 603)
    campo_fixo(canvas, "TELEFONE:", ctx["telefone"], 45, 108, 582, 270)
    campo_fixo(canvas, "E-MAIL:", ctx["email"], 288, 340, 582, 550)
    campo_fixo(canvas, "NOME DO ANIVERSARIANTE:", ctx["aniversariante"], 45, 202, 558, 370)
    campo_fixo(canvas, "IDADE:", ctx["idade"], 385, 432, 558, 550)
    campo_fixo(canvas, "LOCAL:", ctx["local"], 45, 92, 534, 550)
    campo_fixo(canvas, "DATA:", ctx["data"], 45, 82, 512, 190)
    campo_fixo(canvas, "HORARIO:", ctx["inicio"], 215, 280, 512, 335)
    canvas.text(342, 512, "as", size=8)
    canvas.line(358, 510, 430, 510)


def desenhar_clausulas(canvas, clausulas, y, bottom=80):
    for clausula in clausulas:
        if y < bottom:
            break
        y = canvas.wrapped(45, y, clausula, width=128, size=7.2, line_height=9)
        y -= 7
    return y


def desenhar_assinatura(canvas, ctx):
    data = ctx["data_contrato"]
    canvas.text(45, 190, "(    )  SIM         (    ) NAO", size=8, font="F2")
    canvas.text(45, 160, "E por estarem justos e contratados, firmam o presente instrumento em duas (duas) vias iguais.", size=8)
    canvas.text(45, 125, f"Fortaleza, {data.day:02d} de __________________ {data.year}", size=8)
    canvas.line(70, 72, 250, 72)
    canvas.line(325, 72, 515, 72)
    canvas.text(105, 58, "ASS. CLIENTE", size=7, font="F2")
    canvas.text(348, 58, "JOAO BOSCO LISBOA DE MORAIS", size=7, font="F2")


def gerar_pdf_documento(documento):
    logo = carregar_png_rgb(LOGO_PATH)
    canvas = PdfCanvas(tem_logo=bool(logo))
    texto_contrato = documento.contrato_renderizado()

    canvas.add_page()
    desenhar_marca(canvas)
    canvas.text(230, 728, "CONTRATO DE SERVICO", size=12, font="F2")
    y = 700
    for bloco in texto_contrato.splitlines():
        linhas = wrap(bloco, width=108) or [""]
        for linha in linhas:
            if y < 58:
                canvas.add_page()
                desenhar_marca(canvas)
                canvas.text(230, 728, "CONTRATO DE SERVICO", size=12, font="F2")
                y = 700
            canvas.text(45, y, linha, size=8)
            y -= 11
        if bloco.strip():
            y -= 3
    canvas.finish()

    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >>",
    ]
    logo_obj = None
    if logo:
        logo_obj = len(objetos) + 1
        logo_stream = logo["stream"]
        objetos.append(
            (
                f"<< /Type /XObject /Subtype /Image /Width {logo['width']} /Height {logo['height']} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(logo_stream)} >>\n"
                f"stream\n{logo_stream.decode('latin-1')}\nendstream"
            )
        )
    page_refs = []
    for page_commands in canvas.pages:
        page_obj = len(objetos) + 1
        content_obj = page_obj + 1
        page_refs.append(f"{page_obj} 0 R")
        stream = "\n".join(page_commands).encode("latin-1", errors="replace")
        xobject = f" /XObject << /Logo {logo_obj} 0 R >>" if logo_obj else ""
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >>{xobject} >> /Contents {content_obj} 0 R >>"
        )
        objetos.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream")
    objetos[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"

    partes = [b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for indice, objeto in enumerate(objetos, start=1):
        offsets.append(sum(len(parte) for parte in partes))
        partes.append(f"{indice} 0 obj\n{objeto}\nendobj\n".encode("latin-1", errors="replace"))

    xref_inicio = sum(len(parte) for parte in partes)
    xref = ["xref", f"0 {len(objetos) + 1}", "0000000000 65535 f "]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n ")
    xref.append(
        "trailer\n"
        f"<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        "startxref\n"
        f"{xref_inicio}\n"
        "%%EOF\n"
    )
    partes.append("\n".join(xref).encode("latin-1", errors="replace"))
    return b"".join(partes)


def nome_pdf_documento(documento):
    base = "".join(ch if ch.isalnum() else "_" for ch in documento.titulo.lower()).strip("_")
    return f"{base or 'contrato'}.pdf"


def gerar_pdf_relatorio_despesas(titulo, despesas, total):
    canvas = PdfCanvas()
    canvas.add_page()
    y = 790
    canvas.text(45, y, titulo, size=15, font="F2")
    y -= 24
    canvas.text(45, y, f"Total do periodo: R$ {brl(total)}", size=10, font="F2")
    y -= 26

    cabecalho = ["Descricao", "Categoria", "Data", "Vencimento", "Pagamento", "Status", "Valor"]
    larguras = [150, 82, 58, 70, 72, 58, 56]
    x = 45
    for label, largura in zip(cabecalho, larguras):
        canvas.text(x, y, label, size=7, font="F2")
        x += largura
    y -= 10
    canvas.line(45, y, 550, y)
    y -= 14

    for despesa in despesas:
        if y < 62:
            canvas.add_page()
            y = 790
            canvas.text(45, y, titulo, size=13, font="F2")
            y -= 26

        valores = [
            despesa.descricao,
            despesa.categoria or "Sem categoria",
            data_br(despesa.data),
            data_br(despesa.vencimento),
            despesa.get_forma_pagamento_display(),
            despesa.get_status_display(),
            f"R$ {brl(despesa.valor)}",
        ]
        x = 45
        for valor, largura in zip(valores, larguras):
            texto = str(valor or "")
            if len(texto) > 24:
                texto = texto[:21] + "..."
            canvas.text(x, y, texto, size=7)
            x += largura
        y -= 15

    canvas.finish()

    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >>",
    ]
    page_refs = []
    for page_commands in canvas.pages:
        page_obj = len(objetos) + 1
        content_obj = page_obj + 1
        page_refs.append(f"{page_obj} 0 R")
        stream = "\n".join(page_commands).encode("latin-1", errors="replace")
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> /Contents {content_obj} 0 R >>"
        )
        objetos.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream")
    objetos[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"

    partes = [b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for indice, objeto in enumerate(objetos, start=1):
        offsets.append(sum(len(parte) for parte in partes))
        partes.append(f"{indice} 0 obj\n{objeto}\nendobj\n".encode("latin-1", errors="replace"))

    xref_inicio = sum(len(parte) for parte in partes)
    xref = ["xref", f"0 {len(objetos) + 1}", "0000000000 65535 f "]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n ")
    xref.append(
        "trailer\n"
        f"<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        "startxref\n"
        f"{xref_inicio}\n"
        "%%EOF\n"
    )
    partes.append("\n".join(xref).encode("latin-1", errors="replace"))
    return b"".join(partes)
