from django.db import models
from orders.models import Order

class Delivery(models.Model):
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

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='delivery')
    scheduled_date = models.DateField()
    scheduled_time_slot = models.CharField(max_length=20, choices=TIME_SLOTS)
    pickup_address = models.CharField(max_length=255)
    delivery_address = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    driver_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Delivery'
        verbose_name_plural = 'Deliveries'

    def __str__(self):
        return f"Delivery for Order #{self.order.id} ({self.status})"
