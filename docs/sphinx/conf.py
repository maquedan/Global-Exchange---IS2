"""Configuración de Sphinx para la documentación automática del código (PDO).

Sphinx lee los docstrings del código fuente y arma un sitio HTML navegable.
No hay que escribir la documentación a mano: se genera desde el propio código.

Para regenerarla:
    sphinx-build -b html docs/sphinx docs/sphinx/_build
"""
import os
import sys
from pathlib import Path

import django

# --- Django tiene que estar inicializado ANTES de que Sphinx lea los módulos ---
# autodoc importa cada módulo para leer sus docstrings, y los módulos de Django
# (modelos, vistas) fallan si no hay una configuración cargada.
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

# --- Datos del proyecto ---
project = "Global Exchange"
copyright = "2026, Grupo 9 — FP-UNA"
author = "Grupo 9"
release = "1.0.0"
language = "es"

# --- Extensiones ---
extensions = [
    "sphinx.ext.autodoc",      # extrae los docstrings del código
    "sphinx.ext.napoleon",     # entiende docstrings en estilo Google y NumPy
    "sphinx.ext.viewcode",     # agrega un enlace al código fuente de cada función
    "sphinx.ext.intersphinx",  # enlaza con la documentación de Python y Django
]

# Muestra los miembros de cada módulo ordenados como están en el código,
# no alfabéticamente: se lee mejor.
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,   # no listar lo que no tiene docstring
    "show-inheritance": True,
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "django": ("https://docs.djangoproject.com/en/stable/",
               "https://docs.djangoproject.com/en/stable/_objects/"),
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# --- Salida HTML ---
html_theme = "alabaster"
html_static_path = []
