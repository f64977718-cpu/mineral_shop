from django.urls import path
from . import views

app_name = "store"

urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.product_list, name="product_list"),
    path("catalog/<slug:category_slug>/", views.product_list, name="category"),
    path("mineral/<slug:slug>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:mineral_id>/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:mineral_id>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("order/<uuid:public_id>/", views.order_detail, name="order_detail"),
    path("order/<uuid:public_id>/pay/", views.order_pay, name="order_pay"),
    path("webhooks/stripe/", views.webhook_stripe, name="webhook_stripe"),
    path("webhooks/liqpay/", views.webhook_liqpay, name="webhook_liqpay"),
    path("pay/mock/<str:reference>/", views.mock_pay, name="mock_pay"),
]
