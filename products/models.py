from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

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

    def __str__(self):
        return f"{self.name} ({self.producer.username})"
