from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser


class RegisterForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'role', 'password1', 'password2']


class CustomerPostcodeForm(forms.Form):
    postcode = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. BS1 1AA'}),
        label='Your Postcode',
        help_text='Used to show food miles from each producer to you.',
    )