from django import forms
from django.utils import timezone
from datetime import timedelta
from .validators import validate_delivery_date
from .models import RecurringOrder
 
 
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

    delivery_instructions = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'e.g. Leave with reception, ask for chef, call on arrival.',
        }),
        label='Delivery Instructions',
        help_text='Optional. Useful for restaurants, community groups, or hard-to-find addresses.',
    )


class RecurringOrderForm(forms.ModelForm):
    class Meta:
        model = RecurringOrder
        fields = ['name', 'recurrence_day', 'delivery_day', 'delivery_address', 'delivery_instructions']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Weekly veg box'}),
            'delivery_address': forms.Textarea(attrs={'rows': 2, 'placeholder': '12 High Street, Bristol, BS1 1AA'}),
            'delivery_instructions': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional notes'}),
        }
        help_texts = {
            'name': 'Optional label so you can tell your templates apart.',
        }

    def clean(self):
        cleaned = super().clean()
        rec = cleaned.get('recurrence_day')
        deliv = cleaned.get('delivery_day')
        if rec is not None and deliv is not None:
            # delivery_day must be at least 2 days after recurrence_day in the weekly cycle
            gap = (deliv - rec) % 7
            if gap < 2:
                self.add_error(
                    'delivery_day',
                    'Delivery must be at least 2 days after the recurrence day.',
                )
        return cleaned