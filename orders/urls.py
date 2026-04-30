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
    path("history/", views.order_history, name="order_history"),
    path("order/<int:order_id>/reorder/", views.reorder, name="reorder"),
    path("item/<int:item_id>/toggle-packed/", views.toggle_item_packed, name="toggle_item_packed"),
    path("order/<int:order_id>/pack-all/", views.pack_all_items, name="pack_all_items"),
    path("order/<int:order_id>/mark-ready/", views.mark_order_ready, name="mark_order_ready"),
    path("order/<int:order_id>/ship/", views.ship_order, name="ship_order"),
]
