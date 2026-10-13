import logging
import uuid

import stripe
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .cart import Cart
from .forms import CartAddForm, OrderCreateForm
from .models import Category, Mineral, Order, Payment
from .payments import services
from .payments.providers import LiqPayProvider, StripeProvider, get_provider

log = logging.getLogger("store.payments")


# ------------------------------------------------------------------ каталог
def home(request):
    return render(request, "store/home.html", {
        "categories": Category.objects.all(),
        "featured": Mineral.objects.filter(is_featured=True)[:6],
    })


def product_list(request, category_slug=None):
    category = None
    minerals = Mineral.objects.all()
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        minerals = minerals.filter(category=category)
    sort = request.GET.get("sort")
    if sort == "price_asc":
        minerals = minerals.order_by("price")
    elif sort == "price_desc":
        minerals = minerals.order_by("-price")
    return render(request, "store/product_list.html", {
        "category": category, "categories": Category.objects.all(),
        "minerals": minerals, "sort": sort or "",
    })


def product_detail(request, slug):
    mineral = get_object_or_404(Mineral, slug=slug)
    return render(request, "store/product_detail.html", {
        "mineral": mineral,
        "cart_form": CartAddForm(initial={"quantity": 1}),
        "related": Mineral.objects.filter(category=mineral.category).exclude(id=mineral.id)[:4],
        "gallery": mineral.images.all(),
    })


# ------------------------------------------------------------------ кошик
@require_POST
def cart_add(request, mineral_id):
    mineral = get_object_or_404(Mineral, id=mineral_id)
    form = CartAddForm(request.POST)
    if form.is_valid():
        if not mineral.in_stock:
            messages.warning(request, f"«{mineral.name}» немає в наявності.")
        else:
            Cart(request).add(mineral=mineral, quantity=form.cleaned_data["quantity"])
            messages.success(request, f"«{mineral.name}» додано до кошика.")
    return redirect("store:cart_detail")


@require_POST
def cart_remove(request, mineral_id):
    mineral = get_object_or_404(Mineral, id=mineral_id)
    Cart(request).remove(mineral)
    messages.info(request, f"«{mineral.name}» видалено з кошика.")
    return redirect("store:cart_detail")


def cart_detail(request):
    return render(request, "store/cart_detail.html", {"cart": Cart(request)})


# ------------------------------------------------------------------ оформлення та оплата
def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.warning(request, "Ваш кошик порожній — додайте мінерали перед оформленням.")
        return redirect("store:product_list")

    if request.method == "POST":
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            try:
                order = services.create_order_from_cart(cart, form.cleaned_data, settings.PAYMENT_CURRENCY)
            except services.OutOfStock as e:
                messages.error(request, str(e))
                return redirect("store:cart_detail")
            cart.clear()
            if order.payment_method == "cod":
                return redirect(order)
            return _start_payment(request, order)
    else:
        form = OrderCreateForm(initial={"payment_method": "online"})
    return render(request, "store/checkout.html", {"cart": cart, "form": form})


def _start_payment(request, order):
    """Створює спробу оплати й відправляє покупця на сторінку провайдера."""
    try:
        provider = get_provider()
        payment = services.new_payment(order, provider.name)
        checkout_info = provider.create_checkout(payment, order)
    except Exception:
        log.exception("Не вдалося створити платіж для замовлення %s", order.id)
        messages.error(request, "Платіжний сервіс тимчасово недоступний. Замовлення збережено — спробуйте оплатити ще раз.")
        return redirect(order)

    payment.provider_ref = checkout_info.provider_ref
    payment.status = "pending"
    payment.save(update_fields=["provider_ref", "status", "updated_at"])

    if checkout_info.form_action:
        return render(request, "store/payment_redirect.html", {
            "action": checkout_info.form_action, "fields": checkout_info.form_fields})
    return redirect(checkout_info.redirect_url)


def order_detail(request, public_id):
    order = get_object_or_404(Order, public_id=public_id)
    last_payment = order.payments.first()
    waiting = order.status == "awaiting_payment" and bool(
        last_payment and last_payment.status in ("created", "pending") and request.GET.get("return"))
    return render(request, "store/order_detail.html", {
        "order": order, "payment": last_payment, "waiting": waiting,
        "can_pay": order.status == "awaiting_payment",
    })


@require_POST
def order_pay(request, public_id):
    order = get_object_or_404(Order, public_id=public_id)
    if order.status != "awaiting_payment":
        return redirect(order)
    return _start_payment(request, order)


# ------------------------------------------------------------------ вебхуки
@csrf_exempt
@require_POST
def webhook_stripe(request):
    try:
        args = StripeProvider().parse_webhook(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""))
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponseBadRequest("invalid signature")
    if args is None:
        return HttpResponse("ignored")
    result = services.apply_payment_result(**args)
    log.info("stripe %s -> %s", args["event_id"], result)
    return HttpResponse(result)


@csrf_exempt
@require_POST
def webhook_liqpay(request):
    try:
        args = LiqPayProvider().parse_webhook(request.POST.get("data", ""), request.POST.get("signature", ""))
    except (ValueError, KeyError):
        return HttpResponseBadRequest("invalid signature")
    result = services.apply_payment_result(**args)
    log.info("liqpay %s -> %s", args["event_id"], result)
    return HttpResponse(result)


# ------------------------------------------------------------------ mock (лише DEBUG)
def mock_pay(request, reference):
    if not (settings.DEBUG and settings.PAYMENT_PROVIDER == "mock"):
        raise Http404
    payment = get_object_or_404(Payment, reference=reference, provider="mock")
    if request.method == "POST":
        outcome = {"pay": "succeeded", "fail": "failed"}.get(request.POST.get("outcome"))
        if outcome:
            services.apply_payment_result(
                provider="mock", event_id=f"mock-{uuid.uuid4()}", event_type=f"mock.{outcome}",
                reference=payment.reference, status=outcome,
                amount=payment.amount, currency=payment.currency, provider_ref=payment.provider_ref)
        return redirect(payment.order.get_absolute_url() + "?return=1")
    return render(request, "store/mock_pay.html", {"payment": payment})
