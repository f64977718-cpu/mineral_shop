from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from store.models import Order
from store.payments import services


class Command(BaseCommand):
    help = ("Скасовує неоплачені замовлення старші за PAYMENT_PENDING_TTL_MINUTES і повертає товар на склад. "
            "Запускайте ПІСЛЯ reconcile_payments.")

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(minutes=settings.PAYMENT_PENDING_TTL_MINUTES)
        n = 0
        for oid in Order.objects.filter(status="awaiting_payment", created_at__lt=cutoff).values_list("id", flat=True):
            if services.cancel_unpaid_order(oid):
                n += 1
        self.stdout.write(self.style.SUCCESS(f"Скасовано неоплачених замовлень: {n}"))
