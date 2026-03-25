from django.urls import path
from . import views

urlpatterns = [
    path("cart/", views.view_cart, name="view_cart"),
    path("add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("remove/<int:product_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("update/<int:product_id>/", views.update_cart, name="update_cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("confirmation/<int:order_id>/", views.order_confirmation, name="order_confirmation"),
    path("payment/success/", views.payment_success, name="payment_success"),
    path("payment/cancel/", views.payment_cancel, name="payment_cancel"),
    path("webhook/stripe/", views.stripe_webhook, name="stripe_webhook"),
]
