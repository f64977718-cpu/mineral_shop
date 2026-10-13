from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .middleware import write_log


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    if user.is_staff and request is not None and request.path.startswith("/admin/"):
        write_log(request, "login", user=user)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None and user.is_staff and request is not None:
        write_log(request, "logout", user=user)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    if request is not None and request.path.startswith("/admin/"):
        write_log(request, "login_failed", username=str(credentials.get("username", "")))
