from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .auth_jwt import JWT_COOKIE_NAME, validar_token
from .models import AcessoUsuario, PerfilUsuario


PUBLIC_PATH_PREFIXES = (
    "/login/",
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
                user = User.objects.filter(pk=token_data.get("sub"), is_active=True).first()
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
        perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)
        agora = timezone.now()
        perfil.ultimo_acesso = agora
        perfil.online_ate = agora + timedelta(minutes=5)
        perfil.save(update_fields=["ultimo_acesso", "online_ate"])

        ultimo = AcessoUsuario.objects.filter(user=request.user, caminho=request.path).first()
        if ultimo and (agora - ultimo.criado_em).total_seconds() < 60:
            return
        AcessoUsuario.objects.create(
            user=request.user,
            empresa=perfil.empresa,
            caminho=request.path[:220],
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )
