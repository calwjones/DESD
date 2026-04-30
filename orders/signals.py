from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Order


@receiver(pre_save, sender=Order)
def deduct_stock_on_confirm(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return
    if previous.status != "confirmed" and instance.status == "confirmed":
        for item in instance.items.select_related("product").all():
            product = item.product
            product.stock_quantity = max(0, product.stock_quantity - item.quantity)
            product.save()
