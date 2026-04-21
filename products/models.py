from django.conf import settings
from django.db import models


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

    def __str__(self):
        return f"{self.name} ({self.producer.username})"
