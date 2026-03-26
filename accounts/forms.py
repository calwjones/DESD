from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser


class RegisterForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'role', 'password1', 'password2']


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['email', 'postcode']
        widgets = {
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
            'postcode': forms.TextInput(attrs={'placeholder': 'e.g. BS1 1AA'}),
        }
        help_texts = {
            'postcode': 'Used to show food miles from each producer to you. Optional.',
        }