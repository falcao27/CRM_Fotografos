from textwrap import wrap


def pdf_escape(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "")
    )


def gerar_pdf_documento(documento):
    texto = documento.contrato_renderizado()
    titulo = documento.titulo or "Contrato"
    linhas = []
    for linha in texto.splitlines():
        if not linha.strip():
            linhas.append("")
            continue
        linhas.extend(wrap(linha, width=92) or [""])

    preview_linhas = linhas[:34]
    y = 785
    comandos = [
        "BT",
        "/F1 16 Tf",
        f"50 {y} Td",
        f"({pdf_escape(titulo)}) Tj",
        "ET",
    ]
    y -= 28
    comandos.extend(["BT", "/F1 9 Tf", "12 TL", f"50 {y} Td"])
    for linha in preview_linhas:
        comandos.append(f"({pdf_escape(linha)}) Tj")
        comandos.append("T*")
    comandos.append("ET")
    comandos.extend(
        [
            "0.1 0.45 0.38 RG",
            "1 w",
            "45 65 505 690 re",
            "S",
        ]
    )
    stream = "\n".join(comandos).encode("latin-1", errors="replace")

    valor_campo = pdf_escape(texto)
    objetos = [
        "<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [6 0 R] /NeedAppearances true /DR << /Font << /Helv 4 0 R >> >> >> >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R /Annots [6 0 R] >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream",
        (
            "<< /Type /Annot /Subtype /Widget /FT /Tx /T (conteudo_contrato) "
            "/Rect [45 65 550 755] /F 4 /Ff 4096 "
            "/DA (/Helv 9 Tf 0 g) "
            f"/V ({valor_campo}) /DV ({valor_campo}) "
            "/MK << /BC [0.1 0.45 0.38] /BG [1 1 1] >> >>"
        ),
    ]

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
