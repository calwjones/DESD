import logging

from django.db import transaction
from django.db.models.signals import pre_save
from django.dispatch import receiver

from products.models import Product

from .models import Order

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Order)
def deduct_stock_on_confirm(sender, instance, **kwargs):
    """Decrement stock when an Order transitions to `confirmed`.

    B2 fix: locks each Product row with SELECT ... FOR UPDATE so two
    simultaneous webhook-driven confirmations can't both pass a stock
    check and decrement to 0. If stock is insufficient at confirmation
    time we still clamp to 0 (rather than raise) so the customer's order
    isn't left in a stuck state — but we log a warning so a producer or
    admin can reconcile.
    """
    if not instance.pk:
        return
    try:
        previous = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return
    if previous.status == "confirmed" or instance.status != "confirmed":
        return

    with transaction.atomic():
        for item in instance.items.all():
            product = (
                Product.objects
                .select_for_update()
                .get(pk=item.product_id)
            )
            if product.stock_quantity < item.quantity:
                logger.warning(
                    "Order #%s confirmed but only %s unit(s) of '%s' available "
                    "(needed %s). Stock clamped to 0; producer should reconcile.",
                    instance.pk,
                    product.stock_quantity,
                    product.name,
                    item.quantity,
                )
            product.stock_quantity = max(0, product.stock_quantity - item.quantity)
            product.save()
