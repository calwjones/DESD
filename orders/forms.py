from django import forms
from django.utils import timezone
from datetime import timedelta
from .validators import validate_delivery_date


class CheckoutForm(forms.Form):
    
    delivery_address = forms.CharField(
        max_length=500,
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Enter your full delivery address',
            'class': 'form-control'
        }),
        label='Delivery Address'
    )
    
    delivery_date = forms.DateField(
        required=True,
        validators=[validate_delivery_date],
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'min': (timezone.now().date() + timedelta(days=2)).isoformat()
        }),
        label='Delivery Date',
        help_text='Delivery must be at least 48 hours from now'
    )