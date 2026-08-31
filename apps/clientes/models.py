from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models


class Cliente(models.Model):
    """Entidad de cliente para RF001 — Registro de Clientes (GEG9-11)."""

    class Tipo(models.TextChoices):
        FISICA = "FISICA", "Persona física"
        JURIDICA = "JURIDICA", "Persona jurídica"

    class Categoria(models.TextChoices):
        MINORISTA = "MINORISTA", "Minorista"
        CORPORATIVO = "CORPORATIVO", "Corporativo"
        VIP = "VIP", "VIP"

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    categoria = models.CharField(
        max_length=20,
        choices=Categoria.choices,
        default=Categoria.MINORISTA,
        blank=True,
    )

    # Datos exclusivos de personas físicas
    nombres = models.CharField(max_length=100, blank=True)
    apellidos = models.CharField(max_length=100, blank=True)
    documento = models.CharField(max_length=20, blank=True, null=True, unique=True)

    # Datos exclusivos de personas jurídicas
    razon_social = models.CharField(max_length=150, blank=True)
    ruc = models.CharField(max_length=20, blank=True, null=True, unique=True)

    # Datos de contacto
    email = models.EmailField()
    telefono = models.CharField(max_length=30)
    direccion = models.CharField(max_length=255)

    activo = models.BooleanField(default=True, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def clean(self):
        """Valida los datos obligatorios por tipo de cliente para GEG9-11."""
        errores = {}

        if self.tipo == self.Tipo.FISICA:
            if not self.nombres:
                errores["nombres"] = "El nombre es obligatorio."
            if not self.apellidos:
                errores["apellidos"] = "El apellido es obligatorio."
            if not self.documento:
                errores["documento"] = "El documento es obligatorio."

        if self.tipo == self.Tipo.JURIDICA:
            if not self.razon_social:
                errores["razon_social"] = "La razón social es obligatoria."
            if not self.ruc:
                errores["ruc"] = "El RUC es obligatorio."

        if errores:
            raise ValidationError(errores)

    def desactivar(self):
        """Marca el cliente como inactivo sin eliminarlo físicamente."""
        self.activo = False
        self.save(update_fields=["activo"])

    def activar(self):
        """Rehabilita el cliente para operar nuevamente."""
        self.activo = True
        self.save(update_fields=["activo"])

    def __str__(self):
        if self.tipo == self.Tipo.FISICA:
            return f"{self.nombres} {self.apellidos}"
        return self.razon_social


class AsociacionUsuarioCliente(models.Model):
    """Vincula los usuarios de la plataforma con los clientes que operan."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="asociaciones_clientes",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="asociaciones_usuarios",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "cliente"],
                name="asociacion_usuario_cliente_unica",
            ),
        ]
        ordering = ["usuario__username", "cliente__creado_en"]
        verbose_name = "asociación usuario-cliente"
        verbose_name_plural = "asociaciones usuario-cliente"

    def clean(self):
        errores = {}
        if self.usuario_id and not self.usuario.is_active:
            errores["usuario"] = "Solo se pueden asociar usuarios activos."
        if self.cliente_id and not self.cliente.activo:
            errores["cliente"] = "Solo se pueden asociar clientes activos."
        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"{self.usuario} — {self.cliente}"
