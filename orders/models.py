from django.db import models
from django.conf import settings
from products.models import Product


class Order(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("payment_failed", "Payment Failed"),
        ("processing", "Processing"),
        ("dispatched", "Dispatched"),
        ("partially_delivered", "Partially Delivered"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders"
    )

    total = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    delivery_date = models.DateField()

    delivery_address = models.TextField()

    delivery_instructions = models.TextField(
        blank=True,
        default="",
        help_text="Optional notes for the producer / delivery driver "
                  "(access codes, leave-with-neighbour, allergies for the kitchen, etc).",
    )

    stripe_session_id = models.CharField(
        max_length=200,
        blank=True,
        default=""
    )

    tracking_number = models.CharField(
        max_length=50,
        blank=True,
        default=""
    )

    def __str__(self):
        return f"Order #{self.id}"
    
class OrderItem(models.Model):

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    quantity = models.PositiveIntegerField()

    is_packed = models.BooleanField(default=False)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def subtotal(self):
        return self.quantity * self.price

    def __str__(self):
        return f"{self.product} x {self.quantity}"


class Payment(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="payment"
    )

    stripe_session_id = models.CharField(
        max_length=200,
        blank=True,
        default=""
    )

    stripe_payment_intent_id = models.CharField(
        max_length=200,
        blank=True,
        default=""
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    commission_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    producer_net = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    currency = models.CharField(
        max_length=3,
        default="GBP"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Payment for Order #{self.order_id} ({self.status})"


class PaymentSplit(models.Model):

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="splits"
    )

    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_splits"
    )

    settlement = models.ForeignKey(
        "Settlement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="splits"
    )

    gross_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    commission_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    net_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    class Meta:
        unique_together = ("payment", "producer")

    def __str__(self):
        return f"Split: {self.producer.username} £{self.net_amount} (Order #{self.payment.order_id})"


class RecurringOrder(models.Model):
    """TC-018: customer-saved template that auto-generates a pending Order each
    week on `recurrence_day`. Customer then checks out via the normal flow."""

    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recurring_orders',
    )
    name = models.CharField(max_length=200, blank=True, default='')
    recurrence_day = models.IntegerField(
        choices=DAY_CHOICES,
        help_text='Day of the week the order is auto-generated.',
    )
    delivery_day = models.IntegerField(
        choices=DAY_CHOICES,
        help_text='Day of the week to deliver. At least 2 days after recurrence_day.',
    )
    delivery_address = models.TextField()
    delivery_instructions = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        label = self.name or f"#{self.pk}"
        return f"Recurring {label} ({self.get_recurrence_day_display()})"


class RecurringOrderItem(models.Model):
    recurring_order = models.ForeignKey(
        RecurringOrder,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
    )
    quantity = models.PositiveIntegerField()

    class Meta:
        unique_together = ('recurring_order', 'product')

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"


class Settlement(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending Bank Transfer"),
        ("processed", "Processed"),
    ]

    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="settlements"
    )

    period_start = models.DateField()

    period_end = models.DateField()

    gross_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    commission_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    net_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        unique_together = ("producer", "period_start")
        ordering = ["-period_end"]

    def __str__(self):
        return f"Settlement {self.producer.username} {self.period_start}–{self.period_end} £{self.net_amount}"