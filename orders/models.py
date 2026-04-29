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