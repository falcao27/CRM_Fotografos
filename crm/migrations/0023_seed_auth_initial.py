import os

from django.db import migrations
from django.contrib.auth.hashers import make_password


def senha_inicial(variavel):
    # Sem a variavel de ambiente a conta fica sem senha utilizavel, ate ser
    # definida com "python manage.py changepassword <usuario>".
    return make_password(os.environ.get(variavel) or None)


def criar_acessos_iniciais(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Empresa = apps.get_model("crm", "Empresa")
    PerfilUsuario = apps.get_model("crm", "PerfilUsuario")

    empresa, _ = Empresa.objects.get_or_create(
        nome="Joao Bosco Fotografia",
        defaults={
            "email": "joaoboscofotos@gmail.com",
            "telefone": "(85) 98713-7641",
            "documento": "25.165.098/0001-68",
        },
    )

    admin, created = User.objects.get_or_create(
        username="admin_master",
        defaults={
            "email": "admin@crm.local",
            "first_name": "Admin",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    if created:
        admin.password = senha_inicial("CRM_SEED_ADMIN_PASSWORD")
        admin.save()
    PerfilUsuario.objects.get_or_create(user=admin, defaults={"papel": "admin_master"})

    usuario, created = User.objects.get_or_create(
        username="joaobosco",
        defaults={
            "email": "joaoboscofotos@gmail.com",
            "first_name": "Joao Bosco",
            "is_staff": False,
            "is_superuser": False,
        },
    )
    if created:
        usuario.password = senha_inicial("CRM_SEED_EMPRESA_PASSWORD")
        usuario.save()
    PerfilUsuario.objects.get_or_create(user=usuario, defaults={"empresa": empresa, "papel": "empresa_admin"})


def remover_acessos_iniciais(apps, schema_editor):
    User = apps.get_model("auth", "User")
    User.objects.filter(username__in=["admin_master", "joaobosco"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0022_empresa_acessousuario_perfilusuario"),
    ]

    operations = [
        migrations.RunPython(criar_acessos_iniciais, remover_acessos_iniciais),
    ]
