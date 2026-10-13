import logging

from django.conf import settings

log = logging.getLogger(__name__)

SKIP_PREFIXES = ("/admin/jsi18n/", "/admin/autocomplete/")


def client_ip(request):
    if settings.USE_X_FORWARDED_FOR:
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if fwd:
            return fwd.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def write_log(request, event, user=None, username=""):
    from .models import AdminAccessLog
    try:
        AdminAccessLog.objects.create(
            user=user if (user is not None and getattr(user, "pk", None)) else None,
            username=(username or getattr(user, "get_username", lambda: "")())[:150],
            event=event,
            path=(request.path if request else "")[:255],
            method=(request.method if request else "")[:8],
            ip_address=client_ip(request) if request else None,
            user_agent=(request.META.get("HTTP_USER_AGENT", "") if request else "")[:300],
        )
    except Exception:  # журнал ніколи не повинен ламати сайт
        log.exception("Не вдалося записати AdminAccessLog")


class AdminAccessLogMiddleware:
    """Записує в БД кожен перегляд сторінок /admin/ автентифікованим співробітником."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path
        if path.startswith("/admin/") and not path.startswith(SKIP_PREFIXES):
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated and user.is_staff:
                write_log(request, "page_view", user=user)
        return response
