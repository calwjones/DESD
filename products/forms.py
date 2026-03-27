from django import forms
from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'description', 'category', 'price', 'stock_quantity',
            'is_available', 'is_organic', 'allergen_info', 'harvest_date',
            'best_before_date', 'available_from', 'available_until', 'discount_price',
            'image',
        ]
        widgets = {
            'harvest_date': forms.DateInput(attrs={'type': 'date'}),
            'best_before_date': forms.DateInput(attrs={'type': 'date'}),
            'available_from': forms.DateInput(attrs={'type': 'date'}),
            'available_until': forms.DateInput(attrs={'type': 'date'}),
        }
