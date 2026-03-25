from django import forms
from django.utils import timezone
from datetime import timedelta
from .validators import validate_delivery_date
 
 
class CheckoutForm(forms.Form):
 
    postcode = forms.CharField(
        max_length=10,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. BS1 1AA',
            'autocomplete': 'postal-code',
        }),
        label='Postcode'
    )
 
    delivery_address = forms.CharField(
        max_length=500,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. 12 High Street',
        }),
        label='Delivery Address',
        help_text='Enter your house number and street name'
    )
 
    delivery_date = forms.DateField(
        required=True,
        validators=[validate_delivery_date],
        widget=forms.DateInput(attrs={
            'type': 'date',
            'min': (timezone.now().date() + timedelta(days=2)).isoformat()
        }),
        label='Delivery Date',
        help_text='Delivery must be at least 48 hours from now'
    )