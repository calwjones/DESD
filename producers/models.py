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
