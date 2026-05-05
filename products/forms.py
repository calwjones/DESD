from django import forms
from .models import ALLERGEN_CHOICES, Product, Review


class ProductForm(forms.ModelForm):
    allergen_info = forms.MultipleChoiceField(
        choices=ALLERGEN_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Allergens',
    )
    enable_ai_grading = forms.BooleanField(
        required=False,
        initial=True,
        label='Use AI quality grading',
        help_text='Only applies to fruit/vegetables with an uploaded image. Untick to skip.',
    )

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'category', 'price', 'stock_quantity', 'stock_threshold',
            'low_stock_email_alerts',
            'is_available', 'is_organic', 'allergen_info', 'harvest_date',
            'best_before_date', 'available_from', 'available_until', 'discount_price',
            'image',
            'is_surplus', 'surplus_discount_pct', 'surplus_expires_at', 'surplus_note',
        ]
        widgets = {
            'harvest_date': forms.DateInput(attrs={'type': 'date'}),
            'best_before_date': forms.DateInput(attrs={'type': 'date'}),
            'available_from': forms.DateInput(attrs={'type': 'date'}),
            'available_until': forms.DateInput(attrs={'type': 'date'}),
            'surplus_expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'surplus_note': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.allergen_info:
            self.initial['allergen_info'] = [
                a.strip() for a in self.instance.allergen_info.split(',') if a.strip()
            ]

    def clean_allergen_info(self):
        return ','.join(self.cleaned_data.get('allergen_info', []))

    def clean(self):
        cleaned_data = super().clean()
        is_surplus = cleaned_data.get('is_surplus')
        discount_pct = cleaned_data.get('surplus_discount_pct')
        expires_at = cleaned_data.get('surplus_expires_at')

        if is_surplus:
            if not discount_pct:
                self.add_error('surplus_discount_pct', 'A discount percentage is required for surplus listings.')
            elif discount_pct < 5:
                self.add_error('surplus_discount_pct', 'Discount must be at least 5%.')
            elif discount_pct >= 100:
                self.add_error('surplus_discount_pct', 'Discount cannot be 100% or more.')
            if not expires_at:
                self.add_error('surplus_expires_at', 'An expiry time is required for surplus listings.')

        return cleaned_data


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'title', 'body']
        widgets = {
            'rating': forms.Select(choices=[
                (5, '★★★★★ Excellent'),
                (4, '★★★★☆ Good'),
                (3, '★★★☆☆ Average'),
                (2, '★★☆☆☆ Poor'),
                (1, '★☆☆☆☆ Bad'),
            ]),
            'title': forms.TextInput(attrs={'placeholder': 'Sum up your experience (optional)'}),
            'body': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Tell other customers what you thought (optional)'}),
        }
    
    def clean(self):
        cleaned = super().clean()
        title = (cleaned.get('title') or '').strip()
        body = (cleaned.get('body') or '').strip()
        
        if bool(title) != bool(body):
            raise forms.ValidationError(
                "Please provide both a title and review text, or leave both blank."
            )
        
        # Persist stripped values back so DB doesn't store leading/trailing whitespace
        cleaned['title'] = title
        cleaned['body'] = body
        return cleaned