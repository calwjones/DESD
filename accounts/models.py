from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


# Roles that behave as buyers — can browse, favourite, check out, review, reorder
BUYER_ROLES = ('customer', 'community_group', 'restaurant')


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('customer', 'Customer'),
        ('producer', 'Producer'),
        ('logistics', 'Logistics'),
        ('community_group', 'Community Group'),
        ('restaurant', 'Restaurant'),
    ]
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='customer'
    )
    postcode = models.CharField(max_length=10, blank=True, default='')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    avoided_allergens = models.CharField(max_length=200, blank=True, default='')

    @property
    def is_buyer(self):
        return self.role in BUYER_ROLES

    def __str__(self):
        return f"{self.username} ({self.role})"


class FavouriteProducer(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favourites'
    )
    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favourited_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('customer', 'producer')

    def __str__(self):
        return f"{self.customer.username} → {self.producer.username}"