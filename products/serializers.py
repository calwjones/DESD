from rest_framework import serializers
from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    # Flatten related data for easier API consumption
    producer_name = serializers.CharField(source='producer.username', read_only=True)
    # `category` is a CharField with choices (not a FK), so we can't reach a
    # `.name` attribute. Use the human-readable display value instead.
    category_name = serializers.SerializerMethodField()

    def get_category_name(self, obj):
        return obj.get_category_display()

    class Meta:
        model = Product
        # NB: Product model has `created_at` but no `updated_at` — don't list it.
        fields = [
            'id', 'name', 'description', 'price', 'stock_quantity',
            'image', 'producer', 'producer_name', 'category', 'category_name',
            'quality_grade', 'quality_color_score', 'quality_size_score',
            'quality_ripeness_score', 'quality_assessed_at',
            'created_at',
        ]
        read_only_fields = ['producer', 'created_at']