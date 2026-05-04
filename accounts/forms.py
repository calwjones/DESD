from django import forms
from django.contrib.auth.forms import UserCreationForm

from products.models import ALLERGEN_CHOICES

from .models import CustomUser


class RegisterForm(UserCreationForm):
    PUBLIC_ROLES = [
        ('customer', 'Customer'),
        ('producer', 'Producer'),
    ]
    role = forms.ChoiceField(choices=PUBLIC_ROLES)

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'role', 'password1', 'password2']

    def clean_role(self):
        role = self.cleaned_data.get('role')
        valid_public_roles = [choice[0] for choice in self.PUBLIC_ROLES]
        if role not in valid_public_roles:
            raise forms.ValidationError("Invalid role selected.")
        return role


class CustomerProfileForm(forms.ModelForm):
    avoided_allergens = forms.MultipleChoiceField(
        choices=ALLERGEN_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Allergens I want to avoid',
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'postcode', 'avoided_allergens']
        widgets = {
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
            'postcode': forms.TextInput(attrs={'placeholder': 'e.g. BS1 1AA'}),
        }
        help_texts = {
            'postcode': 'Used to show food miles from each producer to you. Optional.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.avoided_allergens:
            self.initial['avoided_allergens'] = [
                a.strip() for a in self.instance.avoided_allergens.split(',') if a.strip()
            ]

    def clean_avoided_allergens(self):
        return ','.join(self.cleaned_data.get('avoided_allergens', []))