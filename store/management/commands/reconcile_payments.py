from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from store.models import Payment
from store.payments import services
from store.payments.providers import get_provider


class Command(BaseCommand):
    help = ("Звіряє «завислі» платежі з провайдером. Страхує від втрачених вебхуків: "
            "якщо клієнт заплатив, а вебхук не дійшов — статус виправиться тут. Запускайте за cron кожні 5 хв.")

    def add_arguments(self, parser):
        parser.add_argument("--min-age", type=int, default=3, help="Перевіряти платежі старші за N хвилин")

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(minutes=opts["min_age"])
        qs = Payment.objects.filter(status__in=["created", "pending"], created_at__lt=cutoff).exclude(provider="mock")
        fixed = checked = 0
        for p in qs:
            checked += 1
            try:
                remote = get_provider(p.provider).fetch_status(p)
            except Exception as e:  # один збій не зупиняє решту
                self.stderr.write(f"{p.reference}: {e}")
                continue
            if remote is None or remote.status == "pending":
                continue
            res = services.apply_payment_result(
                provider=p.provider, event_id=remote.event_id, event_type="reconcile",
                reference=p.reference, status=remote.status, amount=remote.amount,
                currency=remote.currency, provider_ref=remote.provider_ref)
            if res == services.APPLIED:
                fixed += 1
        self.stdout.write(self.style.SUCCESS(f"Перевірено: {checked}, виправлено: {fixed}"))
