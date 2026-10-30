"""Generación de documentos binarios usados por las descargas locales."""


def crear_pdf_texto(texto):
    """Genera un PDF mínimo válido con texto monoespaciado.

    Se usa como representación local del cliente simulado y para el historial
    exportado. El proveedor real devuelve su propio KuDE firmado.
    """
    lineas = []
    for linea in texto.splitlines() or [""]:
        linea = linea.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lineas.append(linea.encode("latin-1", errors="replace")[:110].decode("latin-1"))
    contenido = "BT /F1 9 Tf 36 756 Td " + " 0 -14 Td ".join(
        f"({linea}) Tj" for linea in lineas
    ) + " ET"
    stream = contenido.encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for numero, objeto in enumerate(objetos, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{numero} 0 obj\n".encode())
        pdf.extend(objeto)
        pdf.extend(b"\nendobj\n")
    posicion_xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objetos) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{posicion_xref}\n%%EOF\n".encode()
    )
    return bytes(pdf)
