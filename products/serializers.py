from rest_framework import serializers
from .models import Product

class ProductSerializer(serializers.ModelSerializer):
    # Flatten related data for easier API consumption
    producer_name = serializers.CharField(source='producer.username', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'stock_quantity',
            'image', 'producer', 'producer_name', 'category', 'category_name',
            'quality_grade', 'quality_color_score', 'quality_size_score',
            'quality_ripeness_score', 'quality_assessed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['producer', 'created_at', 'updated_at']