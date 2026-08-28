"""Vistas de autenticación y panel principal (GEG9-24, GEG9-25)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .menu import roles_de


def inicio(request):
    """Página pública: solo el botón para iniciar sesión con Keycloak."""
    if request.user.is_authenticated:
        return redirect("usuarios:panel")
    return render(request, "usuarios/inicio.html")


@login_required
def panel(request):
    """Vista PROTEGIDA.

    El decorador @login_required es el que la protege: si entrás sin sesión,
    Django te manda a LOGIN_URL (= /oidc/authenticate/, o sea, a Keycloak) y
    después te trae de vuelta acá.
    """
    return render(
        request,
        "usuarios/panel.html",
        {"roles": sorted(roles_de(request.user))},
    )
