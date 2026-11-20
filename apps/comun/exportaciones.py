"""Generadores de archivos para reportes administrativos."""
from decimal import Decimal
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.utils import timezone

from apps.facturacion.documentos import crear_pdf_texto


def fecha_generacion():
    return timezone.localtime().strftime("%d/%m/%Y %H:%M")


def crear_pdf_reporte(titulo, encabezados, filas, totales):
    lineas = [titulo, f"Generado: {fecha_generacion()}", "", " | ".join(map(str, encabezados))]
    lineas.append("-" * min(110, len(lineas[-1])))
    lineas.extend(" | ".join(map(str, fila)) for fila in filas)
    lineas.extend(["", "Totales:"])
    lineas.extend(f"{clave}: {valor}" for clave, valor in totales.items())
    return crear_pdf_texto("\n".join(lineas))


def crear_xlsx(nombre_hoja, encabezados, filas, totales, columnas_numericas=()):
    import html

    def celda(indice, valor):
        if indice in columnas_numericas and isinstance(valor, (int, float, Decimal)):
            return f'<c t="n"><v>{valor}</v></c>'
        texto = html.escape(str(valor if valor is not None else ""))
        return f'<c t="inlineStr"><is><t>{texto}</t></is></c>'

    filas_xml = ['<row>' + ''.join(celda(i, v) for i, v in enumerate(encabezados)) + '</row>']
    filas_xml += ['<row>' + ''.join(celda(i, v) for i, v in enumerate(fila)) + '</row>' for fila in filas]
    filas_xml.append('<row>' + celda(0, "Totales") + '</row>')
    filas_xml += ['<row>' + celda(0, k) + celda(1, v) + '</row>' for k, v in totales.items()]
    hoja = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + ''.join(filas_xml) + '</sheetData></worksheet>')
    archivos = {
        '[Content_Types].xml': ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'),
        '_rels/.rels': ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
        'xl/workbook.xml': (f'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{html.escape(nombre_hoja)}" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        'xl/_rels/workbook.xml.rels': ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'),
        'xl/worksheets/sheet1.xml': hoja,
    }
    salida = BytesIO()
    with ZipFile(salida, 'w', ZIP_DEFLATED) as archivo:
        for ruta, contenido in archivos.items():
            archivo.writestr(ruta, contenido)
    return salida.getvalue()
