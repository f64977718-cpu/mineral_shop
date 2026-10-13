"""Ядро обробки замовлень і платежів.

Принципи, що захищають гроші:
  1. Суму замовлення рахує СЕРВЕР за цінами з БД — не браузер і не сесія.
  2. Дані картки ніколи не торкаються нашого сервера (оплата на сторінці провайдера).
  3. Статус «оплачено» ставиться ЛИШЕ після підписаного повідомлення від провайдера
     (webhook) або після серверної звірки (reconcile) — а не за переходом браузера.
  4. Кожна подія записується в PaymentEvent з унікальністю (provider, event_id):
     повторна доставка вебхука не змінює нічого вдруге (ідемпотентність).
  5. Суму і валюту з події звіряємо з тим, що ми створили. Розбіжність → ручна перевірка.
  6. Усе — у транзакціях із блокуванням рядків (select_for_update): без гонок.
"""
import logging
import secrets
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from store.models import Mineral, Order, OrderItem, Payment, PaymentEvent

log = logging.getLogger("store.payments")

# ---- результат apply_payment_result ----
APPLIED = "applied"
DUPLICATE = "duplicate"
UNKNOWN_PAYMENT = "unknown_payment"
IGNORED = "ignored"
NEEDS_REVIEW = "needs_review"


class OutOfStock(Exception):
    pass


# ---------------------------------------------------------------- замовлення / склад
@transaction.atomic
def create_order_from_cart(cart, order_fields, currency):
    """Створює замовлення, перевіряє й резервує залишки. Ціни беруться з БД."""
    ids = sorted(int(i) for i in cart.cart.keys())
    minerals = {m.id: m for m in Mineral.objects.select_for_update().filter(id__in=ids).order_by("id")}

    lines, total = [], Decimal("0")
    for item in cart:
        m = minerals.get(item["mineral"].id) if item.get("mineral") else None
        if m is None:
            raise OutOfStock("Один із товарів більше недоступний.")
        qty = item["quantity"]
        if m.stock < qty:
            raise OutOfStock(f"«{m.name}»: доступно лише {m.stock} шт.")
        lines.append((m, qty))
        total += m.price * qty

    if not lines:
        raise OutOfStock("Кошик порожній.")

    order = Order.objects.create(
        **order_fields,
        total_amount=total,
        currency=currency,
        status="awaiting_payment" if order_fields.get("payment_method") == "online" else "new",
    )
    for m, qty in lines:
        OrderItem.objects.create(order=order, mineral=m, price=m.price, quantity=qty)
        m.stock -= qty
        m.save(update_fields=["stock"])
    return order


def _locked_minerals(order):
    ids = sorted(order.items.values_list("mineral_id", flat=True))
    return {m.id: m for m in Mineral.objects.select_for_update().filter(id__in=ids).order_by("id")}


def release_stock(order):
    """Повертає товар на склад (один раз). Викликати всередині transaction.atomic."""
    if order.stock_released:
        return
    minerals = _locked_minerals(order)
    for it in order.items.all():
        m = minerals[it.mineral_id]
        m.stock += it.quantity
        m.save(update_fields=["stock"])
    order.stock_released = True
    order.save(update_fields=["stock_released"])


def reserve_stock_again(order):
    """Повторне резервування для запізнілої оплати скасованого замовлення."""
    minerals = _locked_minerals(order)
    items = list(order.items.all())
    if any(minerals[i.mineral_id].stock < i.quantity for i in items):
        return False
    for it in items:
        m = minerals[it.mineral_id]
        m.stock -= it.quantity
        m.save(update_fields=["stock"])
    order.stock_released = False
    order.save(update_fields=["stock_released"])
    return True


# ---------------------------------------------------------------- платежі
def new_payment(order, provider):
    return Payment.objects.create(
        order=order,
        provider=provider,
        reference=f"P{order.id}-{secrets.token_hex(8)}",
        amount=order.total_amount,
        currency=order.currency,
        status="created",
    )


@transaction.atomic
def apply_payment_result(*, provider, event_id, event_type, reference, status,
                         amount=None, currency=None, provider_ref="", payload=None):
    """Єдина точка, де змінюється статус платежу. status: succeeded|failed|expired|refunded|pending.

    Безпечна до повторів і до паралельних викликів.
    """
    event, created = PaymentEvent.objects.get_or_create(
        provider=provider, event_id=event_id,
        defaults={"event_type": event_type, "payload": payload or {}},
    )
    if not created:
        log.info("duplicate event %s:%s ignored", provider, event_id)
        return DUPLICATE

    try:
        payment = Payment.objects.select_for_update().select_related("order").get(reference=reference)
    except Payment.DoesNotExist:
        event.result = UNKNOWN_PAYMENT
        event.save(update_fields=["result"])
        log.error("event %s:%s for unknown payment reference %r", provider, event_id, reference)
        return UNKNOWN_PAYMENT

    event.payment = payment
    order = Order.objects.select_for_update().get(pk=payment.order_id)

    if provider_ref and not payment.provider_ref:
        payment.provider_ref = provider_ref

    result = APPLIED
    if status == "succeeded":
        result = _handle_success(payment, order, amount, currency)
    elif status in ("failed", "expired"):
        if payment.status == "succeeded":
            result = IGNORED  # пізня «невдача» ніколи не скасовує вже отриманий платіж
        else:
            payment.status = status
    elif status == "refunded":
        payment.status = "refunded"
        payment.needs_review = True
        payment.note = "Повернення коштів: перевірте замовлення вручну"
    elif status == "pending":
        if payment.status in ("created", "pending"):
            payment.status = "pending"
        else:
            result = IGNORED
    else:
        result = IGNORED

    payment.save()
    event.result = result
    event.save(update_fields=["payment", "result"])
    return result


def _handle_success(payment, order, amount, currency):
    if payment.status == "succeeded":
        return IGNORED  # вже враховано (інша подія про той самий платіж)

    amount_ok = amount is not None and Decimal(amount) == payment.amount
    currency_ok = currency is None or currency.upper() == payment.currency.upper()
    if not (amount_ok and currency_ok):
        payment.needs_review = True
        payment.note = f"Розбіжність суми/валюти: отримано {amount} {currency}, очікувалось {payment.amount} {payment.currency}"
        log.error("PAYMENT MISMATCH %s: %s", payment.reference, payment.note)
        return NEEDS_REVIEW

    payment.status = "succeeded"
    payment.paid_at = timezone.now()

    if order.status == "cancelled":
        # Гроші прийшли вже після скасування. Пробуємо відновити замовлення.
        if order.stock_released and not reserve_stock_again(order):
            payment.needs_review = True
            payment.note = "Оплата надійшла після скасування, а товару вже немає — потрібне повернення коштів"
            log.error("LATE PAYMENT, NO STOCK %s", payment.reference)
            return NEEDS_REVIEW
        order.status = "paid"
        order.paid_at = payment.paid_at
        order.save(update_fields=["status", "paid_at"])
        payment.note = "Оплата надійшла після скасування — замовлення відновлено"
        return APPLIED

    if order.status == "awaiting_payment":
        order.status = "paid"
        order.paid_at = payment.paid_at
        order.save(update_fields=["status", "paid_at"])
    elif order.status == "paid":
        # Друга успішна оплата того самого замовлення = подвійне списання
        payment.needs_review = True
        payment.note = "Подвійна оплата замовлення — потрібне повернення коштів"
        log.error("DOUBLE PAYMENT %s", payment.reference)
        return NEEDS_REVIEW
    return APPLIED


# ---------------------------------------------------------------- життєвий цикл
@transaction.atomic
def cancel_unpaid_order(order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != "awaiting_payment":
        return False
    if order.payments.filter(status="succeeded").exists():
        return False
    order.payments.filter(status__in=["created", "pending"]).update(status="expired")
    order.status = "cancelled"
    order.save(update_fields=["status"])
    release_stock(order)
    return True
