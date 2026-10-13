import copy
from decimal import Decimal
from django.conf import settings
from .models import Mineral


class Cart:
    """Простий кошик на основі сесії користувача."""

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    def add(self, mineral, quantity=1, override_quantity=False):
        mineral_id = str(mineral.id)
        if mineral_id not in self.cart:
            self.cart[mineral_id] = {"quantity": 0, "price": str(mineral.price)}
        if override_quantity:
            self.cart[mineral_id]["quantity"] = quantity
        else:
            self.cart[mineral_id]["quantity"] += quantity
        self.save()

    def save(self):
        self.session.modified = True

    def remove(self, mineral):
        mineral_id = str(mineral.id)
        if mineral_id in self.cart:
            del self.cart[mineral_id]
            self.save()

    def __iter__(self):
        mineral_ids = self.cart.keys()
        minerals = Mineral.objects.filter(id__in=mineral_ids)
        mineral_map = {str(mineral.id): mineral for mineral in minerals}

        # Deep-copy so we never mutate the session-backed dict with
        # non-JSON-serializable values (Decimal, model instances).
        cart = copy.deepcopy(self.cart)
        for mineral_id, item in cart.items():
            item["mineral"] = mineral_map.get(mineral_id)
            item["price"] = Decimal(item["price"])
            item["total_price"] = item["price"] * item["quantity"]
            yield item

    def __len__(self):
        return sum(item["quantity"] for item in self.cart.values())

    def get_total_price(self):
        return sum(Decimal(item["price"]) * item["quantity"] for item in self.cart.values())

    def clear(self):
        del self.session[settings.CART_SESSION_ID]
        self.save()
