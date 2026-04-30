from django.conf import settings
from django.db import models
from orders.models import Order


class Delivery(models.Model):
    """
    Logistics layer for an Order. One Delivery per producer per order, since
    multi-vendor orders involve separate collections from each producer.
    Order-level status is rolled up from constituent Deliveries.
    """
    TIME_SLOTS = [
        ('morning', 'Morning (8am–12pm)'),
        ('afternoon', 'Afternoon (12pm–5pm)'),
        ('evening', 'Evening (5pm–8pm)'),
    ]
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('collected', 'Collected'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='deliveries'
    )
    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='deliveries_to_make'
    )
    scheduled_date = models.DateField(null=True, blank=True)
    scheduled_time_slot = models.CharField(
        max_length=20, choices=TIME_SLOTS, blank=True
    )
    pickup_address = models.CharField(max_length=255, blank=True)
    delivery_address = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='scheduled'
    )
    driver_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Delivery'
        verbose_name_plural = 'Deliveries'
        unique_together = [('order', 'producer')]

    def __str__(self):
        return f"Delivery for Order #{self.order.id} from {self.producer} ({self.status})"

    def transition_to(self, new_status):
        """Move delivery to a new status, cascading effects to parent Order."""
        valid_transitions = {
            'scheduled': ['collected'],
            'collected': ['out_for_delivery'],
            'out_for_delivery': ['delivered'],
            'delivered': [],
        }
        if new_status not in valid_transitions.get(self.status, []):
            raise ValueError(
                f"Cannot transition from {self.status} to {new_status}"
            )

        if new_status == 'collected' and self.order.status != 'dispatched':
            raise ValueError(
                f"Order #{self.order.id} is not yet ready for collection "
                f"(producer status: {self.order.get_status_display()})"
            )

        self.status = new_status
        self.save()

        # Side effects
        if new_status == 'collected':
            # Customer notification: their order is now in motion
            from orders.views import _send_dispatch_email
            _send_dispatch_email(self.order)

        if new_status == 'delivered':
            self._update_parent_order_status()

    def _update_parent_order_status(self):
        """Roll up delivery statuses to parent Order status."""
        deliveries = self.order.deliveries.all()
        all_delivered = all(d.status == 'delivered' for d in deliveries)
        any_delivered = any(d.status == 'delivered' for d in deliveries)

        if all_delivered:
            self.order.status = 'delivered'
            self.order.save()
        elif any_delivered:
            self.order.status = 'partially_delivered'
            self.order.save()