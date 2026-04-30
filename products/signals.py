from django.core.mail import send_mail
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Product


@receiver(pre_save, sender=Product)
def notify_favourites_on_surplus(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = Product.objects.get(pk=instance.pk)
    except Product.DoesNotExist:
        return

    # Only fire when is_surplus transitions False → True
    if previous.is_surplus or not instance.is_surplus:
        return

    from accounts.models import FavouriteProducer
    favourites = FavouriteProducer.objects.filter(
        producer=instance.producer
    ).select_related('customer', 'producer__producer_profile')

    if not favourites.exists():
        return

    try:
        business_name = instance.producer.producer_profile.business_name
    except Exception:
        business_name = instance.producer.username

    expiry_line = ""
    if instance.surplus_expires_at:
        expiry_line = f"\nDeal expires: {instance.surplus_expires_at.strftime('%d %b %Y at %H:%M')}"

    note_line = f"\n\"{instance.surplus_note}\"" if instance.surplus_note else ""

    for fav in favourites:
        send_mail(
            subject=f"Surplus deal from {business_name} — {instance.surplus_discount_pct}% off {instance.name}",
            message=(
                f"Hi {fav.customer.first_name or fav.customer.username},\n\n"
                f"{business_name}, one of your favourite producers, has just added a surplus deal:\n\n"
                f"  {instance.name} — {instance.surplus_discount_pct}% off\n"
                f"  Now: £{instance.current_price} (was £{instance.price})"
                f"{note_line}"
                f"{expiry_line}\n\n"
                f"Log in to the DESD Marketplace to order before the deal expires.\n\n"
                f"— DESD Marketplace"
            ),
            from_email="noreply@desd.local",
            recipient_list=[fav.customer.email],
            fail_silently=True,
        )
