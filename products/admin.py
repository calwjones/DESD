from django.contrib import admin

from .models import Product


class ProductAdmin(admin.ModelAdmin):
    model = Product
    list_display = ['name', 'producer', 'category', 'price', 'is_available', 'stock_quantity']
    list_filter = ['category', 'is_available', 'is_organic']


admin.site.register(Product, ProductAdmin)
