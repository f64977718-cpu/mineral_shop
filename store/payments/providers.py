"""Платіжні провайдери. Усі працюють за схемою «hosted checkout»:
клієнт вводить картку на сторінці провайдера, а нам приходить підписаний webhook."""
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.urls import reverse

ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "ISK"}


def to_minor(amount, currency):
    """Сума в найменших одиницях (копійки/центи) — цілим числом, без float."""
    if currency.upper() in ZERO_DECIMAL:
        return int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor(value, currency):
    if currency.upper() in ZERO_DECIMAL:
        return Decimal(value)
    return (Decimal(value) / 100).quantize(Decimal("0.01"))


@dataclass
class Checkout:
    """Куди відправити покупця: або redirect_url, або автосабміт форми (LiqPay)."""
    provider_ref: str = ""
    redirect_url: str = ""
    form_action: str = ""
    form_fields: dict = field(default_factory=dict)


@dataclass
class RemoteStatus:
    status: str          # succeeded|failed|expired|pending
    event_id: str
    amount: Decimal = None
    currency: str = None
    provider_ref: str = ""


def _abs(path):
    return f"{settings.SITE_URL}{path}"


# ======================================================================= STRIPE
class StripeProvider:
    name = "stripe"

    def _client(self):
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        return stripe

    def create_checkout(self, payment, order):
        stripe = self._client()
        cur = payment.currency.lower()
        lines = [{
            "price_data": {
                "currency": cur,
                "unit_amount": to_minor(it.price, payment.currency),
                "product_data": {"name": it.mineral.name[:120]},
            },
            "quantity": it.quantity,
        } for it in order.items.select_related("mineral")]
        back = _abs(order.get_absolute_url())
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=lines,
            client_reference_id=payment.reference,
            metadata={"payment_reference": payment.reference, "order_id": str(order.id)},
            customer_email=order.email,
            success_url=back + "?return=1",
            cancel_url=back + "?cancelled=1",
            expires_at=int(time.time()) + 3600,
            idempotency_key=str(payment.idempotency_key),
        )
        return Checkout(provider_ref=session.id, redirect_url=session.url)

    # --- webhook
    def parse_webhook(self, payload: bytes, sig_header: str):
        """Перевіряє підпис і повертає dict-аргументи для apply_payment_result (або None)."""
        stripe = self._client()
        # construct_event кидає виняток, якщо підпис хибний або запит надто старий (захист від replay)
        stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        event = json.loads(payload.decode("utf-8"))
        etype = event["type"]
        obj = event["data"]["object"]
        mapping = {
            "checkout.session.completed": "paid_check",
            "checkout.session.async_payment_succeeded": "succeeded",
            "checkout.session.async_payment_failed": "failed",
            "checkout.session.expired": "expired",
        }
        if etype not in mapping:
            return None
        kind = mapping[etype]
        if kind == "paid_check":
            status = "succeeded" if obj.get("payment_status") == "paid" else "pending"
        else:
            status = kind
        cur = (obj.get("currency") or "").upper() or None
        amount = from_minor(obj["amount_total"], cur) if obj.get("amount_total") is not None and cur else None
        return dict(
            provider="stripe", event_id=event["id"], event_type=etype,
            reference=obj.get("client_reference_id") or (obj.get("metadata") or {}).get("payment_reference", ""),
            status=status, amount=amount, currency=cur, provider_ref=obj.get("id", ""),
            payload=event,
        )

    # --- звірка (запасний канал, якщо вебхук загубився)
    def fetch_status(self, payment):
        if not payment.provider_ref:
            return None
        s = self._client().checkout.Session.retrieve(payment.provider_ref).to_dict()
        cur = (s.get("currency") or "").upper() or None
        amount = from_minor(s["amount_total"], cur) if s.get("amount_total") is not None and cur else None
        if s.get("status") == "complete" and s.get("payment_status") == "paid":
            st = "succeeded"
        elif s.get("status") == "expired":
            st = "expired"
        else:
            st = "pending"
        return RemoteStatus(st, f"reconcile:{payment.reference}:{st}", amount, cur, s.get("id", ""))


# ======================================================================= LIQPAY
class LiqPayProvider:
    name = "liqpay"
    CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"
    API_URL = "https://www.liqpay.ua/api/request"

    @staticmethod
    def sign(data_b64: str) -> str:
        raw = (settings.LIQPAY_PRIVATE_KEY + data_b64 + settings.LIQPAY_PRIVATE_KEY).encode("utf-8")
        return base64.b64encode(hashlib.sha1(raw).digest()).decode()

    @staticmethod
    def encode(params: dict) -> str:
        return base64.b64encode(json.dumps(params, ensure_ascii=False).encode("utf-8")).decode()

    def create_checkout(self, payment, order):
        expires = datetime.now(dt_timezone.utc) + timedelta(minutes=settings.PAYMENT_PENDING_TTL_MINUTES - 10)
        params = {
            "public_key": settings.LIQPAY_PUBLIC_KEY,
            "version": 3,
            "action": "pay",
            "amount": float(payment.amount),
            "currency": payment.currency,
            "description": f"Замовлення №{order.id}",
            "order_id": payment.reference,
            "language": "uk",
            "result_url": _abs(order.get_absolute_url()) + "?return=1",
            "server_url": _abs(reverse("store:webhook_liqpay")),
            "expired_date": expires.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if settings.LIQPAY_SANDBOX:
            params["sandbox"] = 1
        data = self.encode(params)
        return Checkout(form_action=self.CHECKOUT_URL, form_fields={"data": data, "signature": self.sign(data)})

    @classmethod
    def _map_status(cls, st):
        if st == "success" or (st == "sandbox" and settings.LIQPAY_SANDBOX):
            return "succeeded"
        if st in ("failure", "error"):
            return "failed"
        if st == "reversed":
            return "refunded"
        return "pending"

    def parse_webhook(self, data_b64: str, signature: str):
        expected = self.sign(data_b64)
        if not hmac.compare_digest(expected, signature or ""):
            raise ValueError("Невірний підпис LiqPay")
        d = json.loads(base64.b64decode(data_b64).decode("utf-8"))
        st = d.get("status", "")
        return dict(
            provider="liqpay",
            event_id=f"{d.get('payment_id') or d.get('order_id')}:{st}",
            event_type=f"status.{st}",
            reference=d.get("order_id", ""),
            status=self._map_status(st),
            amount=Decimal(str(d["amount"])) if d.get("amount") is not None else None,
            currency=d.get("currency"),
            provider_ref=str(d.get("payment_id", "")),
            payload=d,
        )

    def fetch_status(self, payment):
        data = self.encode({"public_key": settings.LIQPAY_PUBLIC_KEY, "version": 3,
                            "action": "status", "order_id": payment.reference})
        body = urllib.parse.urlencode({"data": data, "signature": self.sign(data)}).encode()
        with urllib.request.urlopen(urllib.request.Request(self.API_URL, data=body), timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
        st = d.get("status", "")
        if st in ("", "error") and d.get("result") == "error":
            return None
        mapped = self._map_status(st)
        return RemoteStatus(mapped, f"reconcile:{payment.reference}:{mapped}",
                            Decimal(str(d["amount"])) if d.get("amount") is not None else None,
                            d.get("currency"), str(d.get("payment_id", "")))


# ======================================================================= MOCK (лише DEBUG)
class MockProvider:
    name = "mock"

    def create_checkout(self, payment, order):
        return Checkout(provider_ref=f"mock_{payment.reference}",
                        redirect_url=reverse("store:mock_pay", args=[payment.reference]))

    def fetch_status(self, payment):
        return None


def get_provider(name=None):
    name = (name or settings.PAYMENT_PROVIDER or "").lower()
    if name == "stripe":
        if not settings.STRIPE_SECRET_KEY:
            raise RuntimeError("STRIPE_SECRET_KEY не задано")
        return StripeProvider()
    if name == "liqpay":
        if not (settings.LIQPAY_PUBLIC_KEY and settings.LIQPAY_PRIVATE_KEY):
            raise RuntimeError("LIQPAY_PUBLIC_KEY / LIQPAY_PRIVATE_KEY не задано")
        return LiqPayProvider()
    if name == "mock":
        if not settings.DEBUG:
            raise RuntimeError("Mock-провайдер дозволений лише при DEBUG=True")
        return MockProvider()
    raise RuntimeError("PAYMENT_PROVIDER не налаштовано (stripe | liqpay)")
