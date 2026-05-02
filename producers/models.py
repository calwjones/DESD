from django.conf import settings
from django.db import models


class ProducerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='producer_profile',
    )
    business_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    postcode = models.CharField(max_length=10, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return f"Profile - {self.user.username}"


class Recipe(models.Model):
    SEASON_CHOICES = [
        ('spring', 'Spring'),
        ('summer', 'Summer'),
        ('autumn', 'Autumn'),
        ('winter', 'Winter'),
        ('year_round', 'Year Round'),
    ]

    producer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recipes')
    title = models.CharField(max_length=200)
    description = models.TextField()
    ingredients = models.TextField()
    method = models.TextField()
    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='recipes')
    seasonal_tag = models.CharField(max_length=20, choices=SEASON_CHOICES, default='year_round')
    image = models.ImageField(upload_to='recipes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class FarmStory(models.Model):
    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='farm_stories'
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    image = models.ImageField(upload_to='farm_stories/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Farm Stories'

    def __str__(self):
        return self.title