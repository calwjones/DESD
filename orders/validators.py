from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta


def validate_delivery_date(value):
    """
    Validates that delivery_date is at least 48 hours from now.
    BRFN-35: Enforce 48-hour delivery window.
    """
    min_delivery_date = timezone.now().date() + timedelta(days=2)
    
    if value < min_delivery_date:
        raise ValidationError(
            f'Delivery date must be at least 48 hours from now. '
            f'Earliest available delivery: {min_delivery_date.strftime("%d/%m/%Y")}'
        )