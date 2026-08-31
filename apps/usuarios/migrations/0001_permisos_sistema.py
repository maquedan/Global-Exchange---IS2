# Generated manually for RF011.
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PermisoSistema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.SlugField(help_text="Identificador técnico, por ejemplo: gestionar_clientes.", max_length=80, unique=True)),
                ("nombre", models.CharField(max_length=120)),
                ("descripcion", models.TextField(blank=True)),
            ],
            options={"verbose_name": "permiso del sistema", "verbose_name_plural": "permisos del sistema", "ordering": ["codigo"]},
        ),
        migrations.CreateModel(
            name="PermisoRol",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rol", models.CharField(max_length=255)),
                ("permiso", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="roles", to="usuarios.permisosistema")),
            ],
            options={"verbose_name": "asignación permiso-rol", "verbose_name_plural": "asignaciones permiso-rol"},
        ),
        migrations.AddConstraint(
            model_name="permisorol",
            constraint=models.UniqueConstraint(fields=("rol", "permiso"), name="rol_permiso_unico"),
        ),
    ]
