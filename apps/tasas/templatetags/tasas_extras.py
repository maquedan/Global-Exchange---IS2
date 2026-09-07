"""Filtro de plantilla para mostrar la bandera de una moneda (RF016).

Las banderas se dibujan con SVG propio, no con emojis: los emojis de
bandera dependen de que el sistema operativo tenga una fuente que sepa
combinarlos, y en Windows suelen verse como dos cuadraditos con letras en
vez de la bandera real. El SVG se ve igual en cualquier máquina.
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Código de moneda (ISO 4217) -> código de país (ISO 3166), para saber qué
# bandera dibujar.
PAIS_DE_LA_MONEDA = {
    "PYG": "PY", "USD": "US", "EUR": "EU", "BRL": "BR", "ARS": "AR",
    "GBP": "GB", "JPY": "JP", "CNY": "CN", "CHF": "CH", "CAD": "CA",
    "AUD": "AU", "CLP": "CL", "UYU": "UY", "BOB": "BO", "PEN": "PE",
    "MXN": "MX", "COP": "CO", "KRW": "KR", "INR": "IN", "ZAR": "ZA",
}

_ENVOLTORIO = '<svg viewBox="0 0 24 16" width="22" height="15" style="border-radius:2px;vertical-align:-2px;margin-right:.4rem;flex-shrink:0;">{}</svg>'

# Banderas simplificadas: geometría aproximada, no vexilología exacta.
# Alcanza para que se reconozcan de un vistazo.
_BANDERAS = {
    "PY": '<rect width="24" height="16" fill="#d52b1e"/><rect y="5.33" width="24" height="5.33" fill="#fff"/><rect y="10.67" width="24" height="5.33" fill="#0038a8"/><circle cx="12" cy="8" r="2.6" fill="none" stroke="#006400" stroke-width=".3"/><polygon points="12,6.1 12.441,7.393 13.807,7.413 12.713,8.232 13.117,9.537 12,8.75 10.883,9.537 11.287,8.232 10.193,7.413 11.559,7.393" fill="#f7d117"/>',
    "US": '<rect width="24" height="16" fill="#b22234"/><rect y="1.2" width="24" height="1.2" fill="#fff"/><rect y="3.6" width="24" height="1.2" fill="#fff"/><rect y="6" width="24" height="1.2" fill="#fff"/><rect y="8.4" width="24" height="1.2" fill="#fff"/><rect y="10.8" width="24" height="1.2" fill="#fff"/><rect y="13.2" width="24" height="1.2" fill="#fff"/><rect width="10" height="8.6" fill="#3c3b6e"/>',
    "EU": '<rect width="24" height="16" fill="#003399"/><circle cx="12" cy="8" r="4.2" fill="none" stroke="#ffcc00" stroke-width=".35" stroke-dasharray="1.3,1.3"/>',
    "BR": '<rect width="24" height="16" fill="#009c3b"/><polygon points="12,2.5 21.5,8 12,13.5 2.5,8" fill="#ffdf00"/><circle cx="12" cy="8" r="3" fill="#002776"/>',
    "AR": '<rect width="24" height="16" fill="#fff"/><rect width="24" height="5.33" fill="#74acdf"/><rect y="10.67" width="24" height="5.33" fill="#74acdf"/><circle cx="12" cy="8" r="1.4" fill="#f6b40e"/>',
    "GB": '<rect width="24" height="16" fill="#00247d"/><path d="M0,0 L24,16 M24,0 L0,16" stroke="#fff" stroke-width="2.4"/><path d="M0,0 L24,16 M24,0 L0,16" stroke="#cf142b" stroke-width="1"/><path d="M12,0 V16 M0,8 H24" stroke="#fff" stroke-width="3.6"/><path d="M12,0 V16 M0,8 H24" stroke="#cf142b" stroke-width="1.6"/>',
    "JP": '<rect width="24" height="16" fill="#fff"/><circle cx="12" cy="8" r="4.6" fill="#bc002d"/>',
    "CN": '<rect width="24" height="16" fill="#de2910"/><polygon points="5,3 6,5.5 8.6,5.5 6.4,7 7.2,9.5 5,8 2.8,9.5 3.6,7 1.4,5.5 4,5.5" fill="#ffde00"/>',
    "CH": '<rect width="24" height="16" fill="#d52b1e"/><rect x="10" y="4.5" width="4" height="7" fill="#fff"/><rect x="6.5" y="6.5" width="11" height="3" fill="#fff"/>',
    "CA": '<rect width="24" height="16" fill="#fff"/><rect width="6" height="16" fill="#d52b1e"/><rect x="18" width="6" height="16" fill="#d52b1e"/><polygon points="12,3 13,6.5 16,5.5 14.5,8 16.5,9 13.7,9.6 14,13 12,11 10,13 10.3,9.6 7.5,9 9.5,8 8,5.5 11,6.5" fill="#d52b1e"/>',
    "AU": '<rect width="24" height="16" fill="#00008b"/><rect width="12" height="8" fill="#00247d"/><path d="M0,0 L12,8 M12,0 L0,8" stroke="#fff" stroke-width="1.2"/><path d="M6,0 V8 M0,4 H12" stroke="#fff" stroke-width="1.8"/><path d="M6,0 V8 M0,4 H12" stroke="#cf142b" stroke-width=".8"/>',
    "CL": '<rect width="24" height="16" fill="#fff"/><rect y="8" width="24" height="8" fill="#d52b1e"/><rect width="8" height="8" fill="#0039a6"/><polygon points="4,2.3 4.7,4.2 6.7,4.2 5.1,5.4 5.7,7.3 4,6.1 2.3,7.3 2.9,5.4 1.3,4.2 3.3,4.2" fill="#fff"/>',
    "UY": '<rect width="24" height="16" fill="#fff"/><rect y="1.8" width="24" height="1.8" fill="#48a9dd"/><rect y="5.4" width="24" height="1.8" fill="#48a9dd"/><rect y="9" width="24" height="1.8" fill="#48a9dd"/><rect y="12.6" width="24" height="1.8" fill="#48a9dd"/><rect width="8" height="8" fill="#fff"/><circle cx="4" cy="4" r="2.4" fill="#fcd116"/>',
    "BO": '<rect width="24" height="16" fill="#d52b1e"/><rect y="5.33" width="24" height="5.33" fill="#f9e300"/><rect y="10.67" width="24" height="5.33" fill="#007934"/>',
    "PE": '<rect width="24" height="16" fill="#d91023"/><rect x="7" width="10" height="16" fill="#fff"/>',
    "MX": '<rect width="24" height="16" fill="#006341"/><rect x="8" width="8" height="16" fill="#fff"/><rect x="16" width="8" height="16" fill="#ce1126"/>',
    "CO": '<rect width="24" height="16" fill="#fcd116"/><rect y="8" width="24" height="4" fill="#003893"/><rect y="12" width="24" height="4" fill="#ce1126"/>',
    "KR": '<rect width="24" height="16" fill="#fff"/><circle cx="12" cy="8" r="3.2" fill="#cd2e3a"/><path d="M9,8 A3.2,1.6 0 0 1 15,8 A1.6,1.6 0 0 1 12,8 A1.6,1.6 0 0 0 9,8" fill="#0047a0"/>',
    "IN": '<rect width="24" height="16" fill="#fff"/><rect width="24" height="5.33" fill="#ff9933"/><rect y="10.67" width="24" height="5.33" fill="#138808"/><circle cx="12" cy="8" r="2" fill="none" stroke="#000080" stroke-width=".4"/>',
    "ZA": '<rect width="24" height="16" fill="#fff"/><rect width="24" height="3.2" fill="#e03c31"/><rect y="12.8" width="24" height="3.2" fill="#001489"/><polygon points="0,3.2 10,8 0,12.8" fill="#007a4d"/><polygon points="0,4.8 8,8 0,11.2" fill="#ffb81c"/><polygon points="0,6 6,8 0,10" fill="#000"/>',
}


@register.filter
def bandera(codigo_moneda):
    """Devuelve un SVG chico con la bandera del país de esa moneda.

    Si la moneda no está en el mapeo (una que todavía no contemplamos), no
    rompe nada: devuelve un ícono neutro de cambio de divisas.
    """
    codigo_pais = PAIS_DE_LA_MONEDA.get((codigo_moneda or "").upper())
    contenido = _BANDERAS.get(codigo_pais)
    if not contenido:
        return "💱"
    return mark_safe(_ENVOLTORIO.format(contenido))
