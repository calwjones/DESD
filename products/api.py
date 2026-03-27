from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Product
from .serializers import ProductSerializer

class ProductViewSet(viewsets.ModelViewSet):
    # API for AI quality grading service
    queryset = Product.objects.select_related('producer', 'category').all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=True, methods=['patch'], url_path='quality')
    def update_quality(self, request, pk=None):
        # AI service calls this to update quality scores
        product = self.get_object()
        
        if 'quality_grade' in request.data:
            product.quality_grade = request.data['quality_grade']
        if 'quality_color_score' in request.data:
            product.quality_color_score = request.data['quality_color_score']
        if 'quality_size_score' in request.data:
            product.quality_size_score = request.data['quality_size_score']
        if 'quality_ripeness_score' in request.data:
            product.quality_ripeness_score = request.data['quality_ripeness_score']
        
        product.quality_assessed_at = timezone.now()
        product.save()
        
        return Response(ProductSerializer(product).data)