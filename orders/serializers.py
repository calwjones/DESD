from rest_framework import serializers
from .models import OrderItem

class OrderHistorySerializer(serializers.ModelSerializer):
    # This serializer flattens order data so the AI can easily analyze it
    # Instead of nested JSON, everything is at the top level
    
    # Get order details
    order_id = serializers.IntegerField(source='order.id')
    customer_id = serializers.IntegerField(source='order.customer.id')
    order_date = serializers.DateTimeField(source='order.created_at')
    delivery_date = serializers.DateField(source='order.delivery_date')
    order_status = serializers.CharField(source='order.status')
    
    # Get product details
    product_id = serializers.IntegerField(source='product.id')
    product_name = serializers.CharField(source='product.name')
    product_category = serializers.CharField(source='product.category.name')
    
    # Get producer details
    producer_id = serializers.IntegerField(source='product.producer.id')
    producer_name = serializers.CharField(source='product.producer.username')
    
    class Meta:
        model = OrderItem
        # List all the fields we want in the API response
        fields = [
            'id', 'order_id', 'customer_id', 'order_date', 
            'delivery_date', 'order_status',
            'product_id', 'product_name', 'product_category',
            'producer_id', 'producer_name',
            'quantity', 'price', 'subtotal'
        ]