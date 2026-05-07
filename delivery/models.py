from django.conf import settings
from django.db import models
from orders.models import Order


class Delivery(models.Model):
    """
    Logistics layer for an Order. One Delivery per producer per order, since
    multi-vendor orders involve separate collections from each producer.
    Order-level status is rolled up from constituent Deliveries.
    """

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),       # delivery created, awaiting producer readiness
        ('collected', 'Collected'),       # picked up from producer, in transit on van
        ('out_for_delivery', 'Out for Delivery'),  # active stop on multi-drop round
        ('delivered', 'Delivered'),       # handed to customer
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='deliveries'
    )
    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='deliveries_to_make'
    )
    delivery_address = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='scheduled'
    )
    driver_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    producer_ready_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the producer marked their items ready for collection",
    )
    tracking_number = models.CharField(max_length=30, blank=True)

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

        if new_status == 'collected':
            if not self.producer_ready_at:
                raise ValueError(
                    f"Cannot collect — {self.producer.username} hasn't marked this delivery ready"
                )
            
        self.status = new_status
        self.save()

        # Side effects.
        # NB: `collected` is intentionally silent — the customer was already
        # told about dispatch when the producer marked the delivery ready
        # (see orders.views.ship_order). The `collected` event is internal
        # to the logistics flow and doesn't need a customer email.
        if new_status == 'out_for_delivery':
            from orders.views import _send_out_for_delivery_email
            _send_out_for_delivery_email(self)

        if new_status == 'delivered':
            from orders.views import _send_delivered_email
            _send_delivered_email(self.order)
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