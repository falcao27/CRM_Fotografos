from datetime import timedelta
import os

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .auth_jwt import JWT_COOKIE_NAME, validar_token
from .models import AcessoUsuario, PerfilUsuario


PUBLIC_PATH_PREFIXES = (
    "/login/",
    "/senha/",
    "/cadastro/",
    "/logout/",
    "/static/",
    "/media/",
    "/admin/",
)


class JWTCookieAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if isinstance(getattr(request, "user", None), AnonymousUser):
            token_data = validar_token(request.COOKIES.get(JWT_COOKIE_NAME, ""))
            if token_data:
                user = (
                    User.objects.select_related("perfil_crm", "perfil_crm__empresa")
                    .filter(pk=token_data.get("sub"), is_active=True)
                    .first()
                )
                if user:
                    request.user = user
        return self.get_response(request)


class CRMRouteProtectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "TESTING", False):
            return self.get_response(request)

        if request.path.startswith(PUBLIC_PATH_PREFIXES):
            return self.get_response(request)

        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.get_full_path()}")

        self._registrar_acesso(request)
        return self.get_response(request)

    def _registrar_acesso(self, request):
        agora = timezone.now()
        intervalo_ping = max(int(os.environ.get("CRM_ACCESS_PING_SECONDS", "300")), 60)
        ultimo_ping = request.session.get("crm_access_ping_at")
        if ultimo_ping and agora.timestamp() - ultimo_ping < intervalo_ping:
            return
        request.session["crm_access_ping_at"] = int(agora.timestamp())

        try:
            perfil = request.user.perfil_crm
        except PerfilUsuario.DoesNotExist:
            perfil = None

        if perfil is None:
            perfil, _ = PerfilUsuario.objects.select_related("empresa").get_or_create(user=request.user)
            request.user._state.fields_cache["perfil_crm"] = perfil

        perfil.ultimo_acesso = agora
        perfil.online_ate = agora + timedelta(minutes=5)
        perfil.save(update_fields=["ultimo_acesso", "online_ate"])

        ultimo = AcessoUsuario.objects.filter(user=request.user, caminho=request.path).first()
        if ultimo and (agora - ultimo.criado_em).total_seconds() < intervalo_ping:
            return
        AcessoUsuario.objects.create(
            user=request.user,
            empresa=perfil.empresa,
            caminho=request.path[:220],
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )
