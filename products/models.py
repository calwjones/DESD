from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

ALLERGEN_CHOICES = [
    ('celery', 'Celery'),
    ('gluten', 'Gluten (Wheat, Rye, Barley, Oats)'),
    ('crustaceans', 'Crustaceans'),
    ('eggs', 'Eggs'),
    ('fish', 'Fish'),
    ('lupin', 'Lupin'),
    ('milk', 'Milk'),
    ('molluscs', 'Molluscs'),
    ('mustard', 'Mustard'),
    ('nuts', 'Tree Nuts'),
    ('peanuts', 'Peanuts'),
    ('sesame', 'Sesame'),
    ('soya', 'Soya'),
    ('sulphites', 'Sulphur Dioxide / Sulphites'),
]


class Product(models.Model):
    CATEGORY_CHOICES = [
        ('vegetables', 'Vegetables'),
        ('fruit', 'Fruit'),
        ('dairy', 'Dairy'),
        ('bakery', 'Bakery'),
        ('preserves', 'Preserves'),
        ('seasonal', 'Seasonal Specialities'),
    ]

    producer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    stock_threshold = models.PositiveIntegerField(
        default=0,
        help_text="Show low-stock warning when stock drops to this level or below. Set to 0 to disable.",
    )
    low_stock_email_alerts = models.BooleanField(
        default=False,
        help_text="Email me when this product's stock drops to or below the threshold.",
    )
    low_stock_alerted = models.BooleanField(
        default=False,
        editable=False,  # internal state, never shown in admin/forms
        help_text="Internal: tracks whether we've already sent the alert for the current low-stock state.",
    )
    is_available = models.BooleanField(default=True)
    is_organic = models.BooleanField(default=False)
    allergen_info = models.TextField(blank=True)
    harvest_date = models.DateField(null=True, blank=True)
    best_before_date = models.DateField(null=True, blank=True)
    available_from = models.DateField(null=True, blank=True)
    available_until = models.DateField(null=True, blank=True)
    discount_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)

    # Surplus deal
    is_surplus = models.BooleanField(default=False)
    surplus_discount_pct = models.PositiveIntegerField(null=True, blank=True)
    surplus_expires_at = models.DateTimeField(null=True, blank=True)
    surplus_note = models.TextField(blank=True)

    # AI quality grading (Sprint 3 — AI service will populate these)
    quality_grade = models.CharField(
        max_length=1,
        choices=[('A', 'Grade A'), ('B', 'Grade B'), ('C', 'Grade C')],
        blank=True,
        null=True,
    )
    quality_color_score = models.IntegerField(blank=True, null=True)
    quality_size_score = models.IntegerField(blank=True, null=True)
    quality_ripeness_score = models.IntegerField(blank=True, null=True)
    quality_assessed_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        if not self.low_stock_email_alerts or self.stock_threshold == 0:
            return
        
        just_dropped = self.is_low_stock and not self.low_stock_alerted
        just_recovered = not self.is_low_stock and self.low_stock_alerted
        
        if just_dropped:
            self._send_low_stock_email()
            Product.objects.filter(pk=self.pk).update(low_stock_alerted=True)
            self.low_stock_alerted = True  # keep in-memory consistent
        elif just_recovered:
            Product.objects.filter(pk=self.pk).update(low_stock_alerted=False)
            self.low_stock_alerted = False
            

    def _send_low_stock_email(self):
        from django.core.mail import send_mail
        from django.conf import settings
        
        send_mail(
            subject=f"Low Stock Alert: {self.name} — DESD Marketplace",
            message=(
                f"Hi {self.producer.username},\n\n"
                f"Stock for one of your products has dropped to or below your alert threshold.\n\n"
                f"Product: {self.name}\n"
                f"Current stock: {self.stock_quantity}\n"
                f"Threshold: {self.stock_threshold}\n\n"
                f"Log in to your dashboard to update inventory.\n\n"
                f"DESD Marketplace"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.producer.email],
            fail_silently=True,
    )

    @property
    def is_active_surplus(self):
        if not self.is_surplus:
            return False
        if self.surplus_expires_at and timezone.now() > self.surplus_expires_at:
            return False
        return True

    @property
    def current_price(self):
        if self.is_active_surplus and self.surplus_discount_pct:
            multiplier = Decimal(100 - self.surplus_discount_pct) / Decimal(100)
            return (self.price * multiplier).quantize(Decimal('0.01'))
        return self.price

    @property
    def best_before_warning(self):
        """True if best-before date is within 2 days — triggers customer confirmation."""
        if not self.best_before_date:
            return False
        return 0 <= (self.best_before_date - timezone.now().date()).days <= 2

    @property
    def days_until_best_before(self):
        if not self.best_before_date:
            return None
        return (self.best_before_date - timezone.now().date()).days

    @property
    def allergen_list(self):
        if not self.allergen_info:
            return []
        return [a.strip() for a in self.allergen_info.split(',') if a.strip()]

    @property
    def allergen_display(self):
        lookup = dict(ALLERGEN_CHOICES)
        return ', '.join(lookup.get(a, a.title()) for a in self.allergen_list)
   
    @property
    def is_low_stock(self):
        return self.stock_threshold > 0 and self.stock_quantity <= self.stock_threshold

    def __str__(self):
        return f"{self.name} ({self.producer.username})"

class Review(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='reviews'
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='reviews_written'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('product', 'customer')]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.username} on {self.product.name}: {self.rating}/5"