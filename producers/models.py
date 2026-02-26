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
    location = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    def __str__(self):
        return f"Profile – {self.user.username}"
