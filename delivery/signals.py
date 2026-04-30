from django.db.models.signals import post_save
from django.dispatch import receiver

from orders.models import Order
from .models import Delivery


@receiver(post_save, sender=Order)
def create_deliveries_on_confirm(sender, instance, created, **kwargs):
    """When an Order transitions to 'confirmed', create one Delivery per producer."""
    if instance.status != 'confirmed':
        return
    if instance.deliveries.exists():
        return  # already created, don't duplicate

    # Group OrderItems by producer
    producers = set(
        item.product.producer for item in instance.items.all()
    )
    for producer in producers:
        Delivery.objects.create(
            order=instance,
            producer=producer,
            delivery_address=instance.delivery_address,
        )