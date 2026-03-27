from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import OrderItem
from .serializers import OrderHistorySerializer

class OrderHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    # ReadOnlyModelViewSet = users can only GET data, not POST/PUT/DELETE
    # This is for the AI to read order history, not modify it
    
    serializer_class = OrderHistorySerializer
    permission_classes = [IsAuthenticated]  # Must be logged in to use this API
    
    def get_queryset(self):
        # Start with all order items
        # select_related loads related data in one query (faster than multiple queries)
        queryset = OrderItem.objects.select_related(
            'order',                # Load the order
            'order__customer',      # Load the customer who placed the order
            'product',              # Load the product
            'product__producer',    # Load the producer who sells it
            'product__category'     # Load the product category
        ).order_by('-order__created_at')  # Newest orders first
        
        # Optional date filtering via query parameters
        # Example: /api/order-history/?start_date=2026-01-01
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(order__created_at__gte=start_date)
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(order__created_at__lte=end_date)
        
        return queryset