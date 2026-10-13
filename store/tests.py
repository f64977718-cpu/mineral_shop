import base64
import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from store.models import (AdminAccessLog, Category, Mineral, Order, Payment, PaymentEvent)
from store.payments import services
from store.payments.providers import LiqPayProvider


def make_mineral(stock=5, price="100.00"):
    cat, _ = Category.objects.get_or_create(slug="c", defaults={"name": "C"})
    return Mineral.objects.create(category=cat, name="Тест", slug=f"t{Mineral.objects.count()}",
                                  description="d", price=Decimal(price), stock=stock)


FORM = {"full_name": "Іван", "email": "a@b.ua", "phone": "+380500000000", "city": "Київ",
        "address": "НП 1", "comment": "", "payment_method": "online"}


def place_order(client, mineral, qty=2, **over):
    client.post(f"/cart/add/{mineral.id}/", {"quantity": qty})
    return client.post("/checkout/", {**FORM, **over})


@override_settings(PAYMENT_PROVIDER="mock", DEBUG=True)
class CheckoutAndPaymentFlow(TestCase):
    def test_total_comes_from_db_and_stock_reserved(self):
        m = make_mineral(stock=5, price="100.00")
        c = Client()
        c.post(f"/cart/add/{m.id}/", {"quantity": 2})
        m.price = Decimal("150.00"); m.save()          # ціна змінилась після додавання в кошик
        r = c.post("/checkout/", FORM)
        order = Order.objects.get()
        self.assertEqual(order.total_amount, Decimal("300.00"))   # актуальна ціна з БД
        m.refresh_from_db(); self.assertEqual(m.stock, 3)
        self.assertEqual(order.status, "awaiting_payment")
        self.assertEqual(r.status_code, 302)

    def test_cannot_oversell(self):
        m = make_mineral(stock=1)
        c = Client(); c.post(f"/cart/add/{m.id}/", {"quantity": 2})
        c.post("/checkout/", FORM)
        self.assertEqual(Order.objects.count(), 0)
        m.refresh_from_db(); self.assertEqual(m.stock, 1)

    def test_browser_redirect_alone_does_not_mark_paid(self):
        m = make_mineral(); c = Client(); place_order(c, m)
        order = Order.objects.get()
        c.get(order.get_absolute_url() + "?return=1")   # «успішне повернення» без вебхука
        order.refresh_from_db(); self.assertEqual(order.status, "awaiting_payment")

    def test_mock_payment_success(self):
        m = make_mineral(); c = Client(); place_order(c, m)
        p = Payment.objects.get()
        c.post(f"/pay/mock/{p.reference}/", {"outcome": "pay"})
        order = Order.objects.get(); p.refresh_from_db()
        self.assertEqual((order.status, p.status), ("paid", "succeeded"))

    def test_cod_order_skips_payment(self):
        m = make_mineral(); c = Client(); place_order(c, m, payment_method="cod")
        self.assertEqual(Order.objects.get().status, "new")
        self.assertEqual(Payment.objects.count(), 0)


class Idempotency(TestCase):
    def setUp(self):
        self.m = make_mineral(); c = Client()
        with override_settings(PAYMENT_PROVIDER="mock", DEBUG=True):
            place_order(c, self.m)
        self.p = Payment.objects.get(); self.order = Order.objects.get()

    def apply(self, event_id, status="succeeded", amount=None, currency=None):
        return services.apply_payment_result(
            provider="mock", event_id=event_id, event_type="t", reference=self.p.reference,
            status=status, amount=self.p.amount if amount is None else amount,
            currency=currency or self.p.currency)

    def test_duplicate_event_ignored(self):
        self.assertEqual(self.apply("e1"), services.APPLIED)
        self.assertEqual(self.apply("e1"), services.DUPLICATE)
        self.assertEqual(PaymentEvent.objects.count(), 1)

    def test_second_success_event_is_not_double_counted(self):
        self.apply("e1"); self.assertEqual(self.apply("e2"), services.IGNORED)
        self.assertEqual(Payment.objects.filter(status="succeeded").count(), 1)

    def test_amount_mismatch_flags_review_and_keeps_order_unpaid(self):
        self.assertEqual(self.apply("e1", amount=Decimal("1.00")), services.NEEDS_REVIEW)
        self.p.refresh_from_db(); self.order.refresh_from_db()
        self.assertTrue(self.p.needs_review); self.assertEqual(self.order.status, "awaiting_payment")

    def test_wrong_currency_flags_review(self):
        self.assertEqual(self.apply("e1", currency="USD"), services.NEEDS_REVIEW)

    def test_late_failure_does_not_undo_success(self):
        self.apply("e1"); self.apply("e2", status="failed")
        self.p.refresh_from_db(); self.assertEqual(self.p.status, "succeeded")

    def test_unknown_reference_is_logged_not_crashing(self):
        r = services.apply_payment_result(provider="mock", event_id="x", event_type="t",
                                          reference="nope", status="succeeded", amount=1, currency="UAH")
        self.assertEqual(r, services.UNKNOWN_PAYMENT)

    def test_expire_restores_stock_and_late_payment_restores_order(self):
        Order.objects.filter(pk=self.order.pk).update(created_at=timezone.now() - timezone.timedelta(hours=5))
        call_command("expire_orders")
        self.order.refresh_from_db(); self.m.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled"); self.assertEqual(self.m.stock, 5)
        self.apply("late")   # гроші все ж прийшли
        self.order.refresh_from_db(); self.m.refresh_from_db()
        self.assertEqual(self.order.status, "paid"); self.assertEqual(self.m.stock, 3)

    def test_late_payment_without_stock_needs_refund_review(self):
        Order.objects.filter(pk=self.order.pk).update(created_at=timezone.now() - timezone.timedelta(hours=5))
        call_command("expire_orders")
        Mineral.objects.filter(pk=self.m.pk).update(stock=0)
        self.assertEqual(self.apply("late"), services.NEEDS_REVIEW)


@override_settings(STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET="whsec_test", PAYMENT_PROVIDER="stripe")
class StripeWebhook(TestCase):
    def setUp(self):
        m = make_mineral()
        c = Client()
        with override_settings(PAYMENT_PROVIDER="mock", DEBUG=True):
            place_order(c, m)
        self.order = Order.objects.get()
        self.p = Payment.objects.get(); self.p.provider = "stripe"; self.p.save()

    def signed(self, payload: dict):
        body = json.dumps(payload).encode()
        t = int(time.time())
        sig = hmac.new(b"whsec_test", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
        return body, f"t={t},v1={sig}"

    def event(self, etype="checkout.session.completed", eid="evt_1", amount=20000, paid="paid"):
        return {"id": eid, "object": "event", "type": etype, "data": {"object": {
            "id": "cs_1", "object": "checkout.session", "client_reference_id": self.p.reference,
            "amount_total": amount, "currency": "uah", "payment_status": paid, "status": "complete"}}}

    def post(self, body, sig):
        return Client().post("/webhooks/stripe/", body, content_type="application/json", HTTP_STRIPE_SIGNATURE=sig)

    def test_valid_signature_marks_paid_and_duplicate_is_safe(self):
        body, sig = self.signed(self.event())
        self.assertEqual(self.post(body, sig).status_code, 200)
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "paid")
        r2 = self.post(body, sig)                     # Stripe повторює доставку
        self.assertEqual(r2.content.decode(), "duplicate")
        self.assertEqual(PaymentEvent.objects.count(), 1)

    def test_forged_signature_rejected(self):
        body, _ = self.signed(self.event())
        self.assertEqual(self.post(body, "t=1,v1=deadbeef").status_code, 400)
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "awaiting_payment")

    def test_wrong_amount_not_paid(self):
        body, sig = self.signed(self.event(amount=100))
        self.post(body, sig)
        self.order.refresh_from_db(); self.p.refresh_from_db()
        self.assertEqual(self.order.status, "awaiting_payment"); self.assertTrue(self.p.needs_review)

    def test_unpaid_completed_session_stays_pending(self):
        body, sig = self.signed(self.event(paid="unpaid"))
        self.post(body, sig)
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "awaiting_payment")


@override_settings(LIQPAY_PUBLIC_KEY="pub", LIQPAY_PRIVATE_KEY="priv", PAYMENT_PROVIDER="liqpay")
class LiqPayWebhook(TestCase):
    def setUp(self):
        m = make_mineral(); c = Client()
        with override_settings(PAYMENT_PROVIDER="mock", DEBUG=True):
            place_order(c, m)
        self.order = Order.objects.get(); self.p = Payment.objects.get()
        self.p.provider = "liqpay"; self.p.save()

    def payload(self, status="success", amount=200):
        data = LiqPayProvider.encode({"status": status, "order_id": self.p.reference, "amount": amount,
                                      "currency": "UAH", "payment_id": 777})
        return {"data": data, "signature": LiqPayProvider.sign(data)}

    def test_success(self):
        self.assertEqual(Client().post("/webhooks/liqpay/", self.payload()).status_code, 200)
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "paid")

    def test_bad_signature(self):
        pl = self.payload(); pl["signature"] = "AAAA"
        self.assertEqual(Client().post("/webhooks/liqpay/", pl).status_code, 400)
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "awaiting_payment")

    def test_tampered_data_with_old_signature_rejected(self):
        pl = self.payload(amount=1)
        forged = LiqPayProvider.encode({"status": "success", "order_id": self.p.reference, "amount": 200,
                                        "currency": "UAH", "payment_id": 777})
        self.assertEqual(Client().post("/webhooks/liqpay/", {"data": forged, "signature": pl["signature"]}).status_code, 400)

    def test_sandbox_status_not_accepted_in_live_mode(self):
        Client().post("/webhooks/liqpay/", self.payload(status="sandbox"))
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "awaiting_payment")

    def test_reconcile_recovers_lost_webhook(self):
        Payment.objects.filter(pk=self.p.pk).update(created_at=timezone.now() - timezone.timedelta(minutes=30))
        remote = mock.Mock(status="succeeded", event_id="reconcile:x", amount=Decimal("200.00"),
                           currency="UAH", provider_ref="777")
        with mock.patch.object(LiqPayProvider, "fetch_status", return_value=remote):
            call_command("reconcile_payments")
        self.order.refresh_from_db(); self.assertEqual(self.order.status, "paid")


class AdminLogging(TestCase):
    def setUp(self):
        self.u = get_user_model().objects.create_superuser("boss", "b@b.ua", "Str0ng-pass-123")

    def test_login_pageview_and_failed_login_are_recorded(self):
        c = Client()
        c.post("/admin/login/", {"username": "boss", "password": "wrong"})
        self.assertTrue(AdminAccessLog.objects.filter(event="login_failed", username="boss").exists())
        c.post("/admin/login/", {"username": "boss", "password": "Str0ng-pass-123"})
        self.assertTrue(AdminAccessLog.objects.filter(event="login", user=self.u).exists())
        c.get("/admin/store/mineral/")
        row = AdminAccessLog.objects.filter(event="page_view", path="/admin/store/mineral/").first()
        self.assertIsNotNone(row); self.assertEqual(row.ip_address, "127.0.0.1")

    def test_anonymous_admin_visit_redirects_to_login(self):
        r = Client().get("/admin/")
        self.assertEqual(r.status_code, 302); self.assertIn("/admin/login/", r["Location"])

    def test_regular_shop_pages_not_logged(self):
        c = Client(); c.force_login(self.u); c.get("/catalog/")
        self.assertFalse(AdminAccessLog.objects.filter(event="page_view").exists())


class PagesRender(TestCase):
    def test_pages(self):
        m = make_mineral()
        for url in ["/", "/catalog/", "/catalog/c/", f"/mineral/{m.slug}/", "/cart/"]:
            self.assertEqual(Client().get(url).status_code, 200, url)

    def test_photo_url_used_when_set(self):
        m = make_mineral(); m.image_url = "https://example.com/a.jpg"; m.save()
        self.assertIn("https://example.com/a.jpg", Client().get(f"/mineral/{m.slug}/").content.decode())
