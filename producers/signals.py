from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import CustomUser
from .models import ProducerProfile


@receiver(post_save, sender=CustomUser)
def create_producer_profile(sender, instance, created, **kwargs):
    if instance.role == 'producer':
        ProducerProfile.objects.get_or_create(user=instance)
