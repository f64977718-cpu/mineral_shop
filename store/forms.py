from django import forms
from .models import Order

PRODUCT_QUANTITY_CHOICES = [(i, str(i)) for i in range(1, 11)]


class CartAddForm(forms.Form):
    quantity = forms.TypedChoiceField(choices=PRODUCT_QUANTITY_CHOICES, coerce=int, label="Кількість")


class OrderCreateForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["full_name", "email", "phone", "city", "address", "comment", "payment_method"]
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "Ім'я та прізвище"}),
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com"}),
            "phone": forms.TextInput(attrs={"placeholder": "+380 __ ___ __ __"}),
            "city": forms.TextInput(attrs={"placeholder": "Місто"}),
            "address": forms.TextInput(attrs={"placeholder": "Відділення Нової пошти або адреса"}),
            "comment": forms.Textarea(attrs={"placeholder": "Побажання до замовлення", "rows": 3}),
            "payment_method": forms.RadioSelect,
        }
