from django import forms

from .models import ProducerProfile


class ProducerProfileForm(forms.ModelForm):
    class Meta:
        model = ProducerProfile
        fields = ['business_name', 'bio', 'location', 'contact_email', 'website']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
        }
